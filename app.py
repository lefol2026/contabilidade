import io
import os
import re
import xml.etree.ElementTree as ET
import zipfile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd
import streamlit as st

try:
    import pypdf

    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

DATA_FILE = "dados_consolidados.parquet"
FOLDER_ID = "1s7BomVcbrpDfEMAjOXUNt593VuJ_KOHs"

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA
# ==========================================
st.set_page_config(
    page_title="Executive B.I. - Apuração Fiscal", page_icon="👑", layout="wide"
)

EMPRESAS_CONFIG = {
    "MCRTOTTI LTDA / BRA": {
        "icms": 0.06,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
    },
    "BR TOTTI LTDA / BW": {
        "icms": 0.06,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
    },
    "RTX IMPORTS COMERCIAL LTDA": {
        "icms": 0.06,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
    },
    "BG ADESIVOS LTDA": {
        "icms": 0.0439,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
    },
}

MAPA_PASTAS_MESES = {
    "0745": (1, "01-Jan"),
    "0746": (2, "02-Fev"),
    "0747": (3, "03-Mar"),
    "0748": (4, "04-Abr"),
    "0749": (5, "05-Mai"),
    "0750": (6, "06-Jun"),
    "0751": (7, "07-Jul"),
    "0752": (8, "08-Ago"),
    "0753": (9, "09-Set"),
    "0754": (10, "10-Out"),
    "0755": (11, "11-Nov"),
    "0756": (12, "12-Dez"),
}


# ==========================================
# 2. FUNÇÕES DE EXTRAÇÃO ROBUSTAS
# ==========================================
def fmt_moeda(val):
    if abs(val) >= 1_000_000:
        return f"R$ {val/1_000_000:,.2f} Mi"
    elif abs(val) >= 1_000:
        return f"R$ {val/1_000:,.1f} K"
    return f"R$ {val:,.2f}"


def fmt_brl(val):
    return (
        f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )


def extrair_valor_xml(bytes_content):
    """Remove namespaces e busca qualquer tag de valor da SEFAZ/NFS-e"""
    try:
        # Limpeza de namespaces
        xml_str = bytes_content.decode("utf-8", errors="ignore")
        xml_clean = re.sub(r'\sxmlns="[^"]+"', "", xml_str, count=1)
        root = ET.fromstring(xml_clean)

        for elem in root.iter():
            if "}" in elem.tag:
                elem.tag = elem.tag.split("}", 1)[1]

        # Prioridade de tags de valor
        for tag in [
            ".//vNF",
            ".//vProd",
            ".//vServ",
            ".//vLiquido",
            ".//ValorServicos",
        ]:
            el = root.find(tag)
            if el is not None and el.text:
                try:
                    v = float(el.text.replace(",", "."))
                    if v > 0:
                        return v
                except ValueError:
                    continue
    except Exception:
        pass
    return 0.0


def extrair_valor_pdf(bytes_content):
    if not HAS_PYPDF:
        return 0.0
    try:
        reader = pypdf.PdfReader(io.BytesIO(bytes_content))
        text = "".join(page.extract_text() or "" for page in reader.pages)
        valores = re.findall(r"VALOR\s+TOTAL[^\d]*([\d\.\,]+)", text.upper())
        if not valores:
            valores = re.findall(r"R\$\s*([\d\.\,]+)", text)

        maior_val = 0.0
        for v in valores:
            try:
                v_c = float(v.replace(".", "").replace(",", "."))
                if v_c > maior_val:
                    maior_val = v_c
            except Exception:
                pass
        return maior_val
    except Exception:
        return 0.0


def MapearMetadados(caminho_str):
    cam_upper = caminho_str.upper()

    # Identificar Empresa
    emp_especifica = "MCRTOTTI LTDA / BRA"
    if "RTX" in cam_upper:
        emp_especifica = "RTX IMPORTS COMERCIAL LTDA"
    elif "BR_TOTTI" in cam_upper or "BW" in cam_upper:
        emp_especifica = "BR TOTTI LTDA / BW"
    elif "BG" in cam_upper or "ADESIVOS" in cam_upper:
        emp_especifica = "BG ADESIVOS LTDA"

    # Identificar Operacao
    eh_entrada = any(
        t in cam_upper for t in ["ENTRADA", "COMPRA", "FORNECEDOR"]
    )
    tipo_op = "Compra (Entrada)" if eh_entrada else "Venda (Saida)"

    # Identificar Mês
    mes_num, mes_nome = 3, "03-Mar"
    for pasta_key, (m_num, m_nome) in MAPA_PASTAS_MESES.items():
        if pasta_key in caminho_str:
            mes_num, mes_nome = m_num, m_nome
            break

    return emp_especifica, tipo_op, mes_num, mes_nome


# ==========================================
# 3. MOTOR DE PROCESSAMENTO E CACHE
# ==========================================
@st.cache_data(ttl=86400)
def carregar_ou_gerar_dados():
    if os.path.exists(DATA_FILE):
        try:
            return pd.read_parquet(DATA_FILE)
        except Exception:
            pass

    if "gdrive" not in st.secrets:
        st.error(
            "⚠️ A chave [gdrive] não foi encontrada nas Secrets do Streamlit!"
        )
        return pd.DataFrame()

    progress_bar = st.progress(0)
    status_text = st.empty()
    status_text.info(
        "🚀 Autenticando no Google Drive e mapeando os 1.341 arquivos..."
    )

    info = dict(st.secrets["gdrive"])
    if "folder_id" in info:
        info.pop("folder_id")
    if "token_uri" not in info:
        info["token_uri"] = "https://oauth2.googleapis.com/token"

    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/drive.readonly"]
    )
    service = build("drive", "v3", credentials=creds)

    def listar_recursivo(folder_id, caminho=""):
        arqs = []
        q = f"'{folder_id}' in parents and trashed = false"
        res = (
            service.files()
            .list(q=q, fields="files(id, name, mimeType)", pageSize=1000)
            .execute()
        )
        for item in res.get("files", []):
            p = f"{caminho}/{item['name']}" if caminho else item["name"]
            if item["mimeType"] == "application/vnd.google-apps.folder":
                arqs.extend(listar_recursivo(item["id"], p))
            elif not item["mimeType"].startswith(
                "application/vnd.google-apps."
            ):
                arqs.append({"id": item["id"], "caminho": p, "nome": item["name"]})
        return arqs

    arquivos = listar_recursivo(FOLDER_ID)
    total = len(arquivos)
    registros = []

    for idx, item in enumerate(arquivos, start=1):
        progress_bar.progress(idx / total)
        status_text.info(
            f"Processando [{idx}/{total}]: {item['nome'][:35]}... (Validas:"
            f" {len(registros)})"
        )

        try:
            request = service.files().get_media(fileId=item["id"])
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            fh.seek(0)
            b = fh.read()

            nome_arq = item["nome"]
            fn_lower = nome_arq.lower()

            # Processamento de ZIP
            if fn_lower.endswith(".zip"):
                try:
                    with zipfile.ZipFile(io.BytesIO(b)) as z:
                        for zinfo in z.infolist():
                            if (
                                zinfo.filename.startswith("__MACOSX")
                                or zinfo.is_dir()
                            ):
                                continue
                            z_fn = zinfo.filename.lower()
                            val_zip = 0.0
                            if z_fn.endswith(".xml"):
                                val_zip = extrair_valor_xml(z.read(zinfo))
                            elif z_fn.endswith(".pdf"):
                                val_zip = extrair_valor_pdf(z.read(zinfo))

                            if val_zip > 0:
                                emp, op, m_num, m_nome = MapearMetadados(
                                    item["caminho"] + "/" + zinfo.filename
                                )
                                registros.append({
                                    "Arquivo": zinfo.filename.split("/")[-1],
                                    "Caminho": item["caminho"],
                                    "Mes_Num": m_num,
                                    "Mês": m_nome,
                                    "Ano": 2026,
                                    "Tipo Operacao": op,
                                    "Valor": float(val_zip),
                                    "Empresa": emp,
                                    "Origem": "ZIP / Drive",
                                })
                except Exception:
                    pass

            # Processamento de XML Direto
            elif fn_lower.endswith(".xml"):
                val_xml = extrair_valor_xml(b)
                if val_xml > 0:
                    emp, op, m_num, m_nome = MapearMetadados(item["caminho"])
                    registros.append({
                        "Arquivo": nome_arq,
                        "Caminho": item["caminho"],
                        "Mes_Num": m_num,
                        "Mês": m_nome,
                        "Ano": 2026,
                        "Tipo Operacao": op,
                        "Valor": float(val_xml),
                        "Empresa": emp,
                        "Origem": "XML / Drive",
                    })

            # Processamento de PDF Direto
            elif fn_lower.endswith(".pdf"):
                val_pdf = extrair_valor_pdf(b)
                if val_pdf > 0:
                    emp, op, m_num, m_nome = MapearMetadados(item["caminho"])
                    registros.append({
                        "Arquivo": nome_arq,
                        "Caminho": item["caminho"],
                        "Mes_Num": m_num,
                        "Mês": m_nome,
                        "Ano": 2026,
                        "Tipo Operacao": op,
                        "Valor": float(val_pdf),
                        "Empresa": emp,
                        "Origem": "PDF / Drive",
                    })

        except Exception:
            continue

    status_text.empty()
    progress_bar.empty()

    df = pd.DataFrame(registros)
    if not df.empty:
        df.to_parquet(DATA_FILE, index=False)
    return df


# ==========================================
# 4. INTERFACE DO PAINEL (DASHBOARD)
# ==========================================
st.title("👑 Executive B.I. — Apuração Fiscal & Conciliação")

df_raw = carregar_ou_gerar_dados()

if not df_raw.empty:
    st.success(
        f"✅ Base consolidada com sucesso! Total de {len(df_raw)} documentos"
        " auditados."
    )

    col_emp, col_mes = st.columns(2)
    with col_emp:
        st.markdown("### 🏢 Empresa:")
        empresas_opcoes = ["TODAS AS EMPRESAS (GRUPO)"] + list(
            EMPRESAS_CONFIG.keys()
        )
        empresa_sel = st.selectbox(
            "Selecione a Empresa",
            empresas_opcoes,
            label_visibility="collapsed",
        )

    with col_mes:
        st.markdown("### 📅 Mês:")
        meses_opcoes = ["Consolidado Anual"] + sorted(
            list(df_raw["Mês"].unique())
        )
        mes_sel = st.selectbox(
            "Selecione o Mês", meses_opcoes, label_visibility="collapsed"
        )

    df_filtrado = df_raw.copy()
    if empresa_sel != "TODAS AS EMPRESAS (GRUPO)":
        df_filtrado = df_filtrado[df_filtrado["Empresa"] == empresa_sel]
    if mes_sel != "Consolidado Anual":
        df_filtrado = df_filtrado[df_filtrado["Mês"] == mes_sel]

    df_vendas = df_filtrado[df_filtrado["Tipo Operacao"] == "Venda (Saida)"]
    fat_bruto = df_vendas["Valor"].sum()
    compras_tot = df_filtrado[
        df_filtrado["Tipo Operacao"] == "Compra (Entrada)"
    ]["Valor"].sum()

    icms, piscofins, irpjcsll = 0.0, 0.0, 0.0
    for _, row in df_vendas.iterrows():
        emp = row["Empresa"]
        v = row["Valor"]
        if emp in EMPRESAS_CONFIG:
            cfg = EMPRESAS_CONFIG[emp]
            icms += v * cfg["icms"]
            piscofins += v * (cfg["pis"] + cfg["cofins"])
            irpjcsll += v * (cfg["irpj"] + cfg["csll"])

    tot_impostos = icms + piscofins + irpjcsll
    aliquota_efetiva = (
        (tot_impostos / fat_bruto * 100) if fat_bruto > 0 else 0.0
    )

    st.markdown("---")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    with c1:
        st.metric("💰 FATURAMENTO", fmt_moeda(fat_bruto), fmt_brl(fat_bruto))
    with c2:
        st.metric("🛒 COMPRAS", fmt_moeda(compras_tot), fmt_brl(compras_tot))
    with c3:
        st.metric("🏛️ ICMS TTS", fmt_moeda(icms))
    with c4:
        st.metric("📊 PIS / COFINS", fmt_moeda(piscofins))
    with c5:
        st.metric("⚖️ IRPJ / CSLL", fmt_moeda(irpjcsll))
    with c6:
        st.metric("🚨 TOTAL IMPOSTOS", fmt_moeda(tot_impostos))

    st.markdown("---")
    st.dataframe(
        df_filtrado[[
            "Arquivo",
            "Origem",
            "Empresa",
            "Mês",
            "Tipo Operacao",
            "Valor",
            "Caminho",
        ]],
        use_container_width=True,
    )
else:
    st.warning(
        "Nenhum documento fiscal foi validado. Verifique se a pasta do Google"
        " Drive contém arquivos XML/PDF válidos."
    )
