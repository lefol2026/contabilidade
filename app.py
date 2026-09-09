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

DATA_FILE = "dados_consolidados.parquet"
FOLDER_ID = "1s7BomVcbrpDfEMAjOXUNt593VuJ_KOHs"

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA & CSS
# ==========================================
st.set_page_config(
    page_title="Executive B.I. - Auditoria Fiscal",
    page_icon="👑",
    layout="wide",
)

st.markdown(
    """
    <style>
    .kpi-card {
        background: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 10px 12px;
        box-shadow: 0px 2px 4px rgba(0,0,0,0.05);
        height: 130px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .kpi-title { font-size: 0.72rem; font-weight: 700; color: #555; text-transform: uppercase; }
    .kpi-value { font-size: 1.25rem; font-weight: 800; color: #111; white-space: nowrap; }
    .kpi-sub { font-size: 0.70rem; color: #00875A; font-weight: 600; }
    </style>
""",
    unsafe_allow_html=True,
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


# ==========================================
# 2. PROCESSADOR INTEGRADO VIA STREAMLIT
# ==========================================
@st.cache_data(ttl=86400)
def carregar_ou_gerar_dados():
    if os.path.exists(DATA_FILE):
        return pd.read_parquet(DATA_FILE)

    if "gdrive" not in st.secrets:
        st.error(
            "⚠️ Configuração de credenciais do Google Drive não encontrada no"
            " Secrets do Streamlit Cloud."
        )
        return pd.DataFrame()

    progress_bar = st.progress(0)
    status_text = st.empty()
    status_text.info("🚀 Conectando ao Google Drive para consolidar notas...")

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
    status_text.info(
        f"📁 {total} arquivos encontrados. Processando faturamento..."
    )

    registros = []
    for idx, item in enumerate(arquivos, start=1):
        progress_bar.progress(idx / total)
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
            cam_upper = item["caminho"].upper()

            valor_final = 0.0
            if fn_lower.endswith(".xml"):
                try:
                    root = ET.fromstring(b)
                    for elem in root.iter():
                        if "}" in elem.tag:
                            elem.tag = elem.tag.split("}", 1)[1]
                    v_nf = root.find(".//vNF")
                    if v_nf is not None and v_nf.text:
                        valor_final = float(v_nf.text)
                    else:
                        v_prod = root.find(".//vProd")
                        if v_prod is not None and v_prod.text:
                            valor_final = float(v_prod.text)
                except Exception:
                    pass

            if valor_final > 0:
                emp_especifica = "MCRTOTTI LTDA / BRA"
                if "RTX" in cam_upper:
                    emp_especifica = "RTX IMPORTS COMERCIAL LTDA"
                elif "BR_TOTTI" in cam_upper or "BW" in cam_upper:
                    emp_especifica = "BR TOTTI LTDA / BW"
                elif "BG" in cam_upper or "ADESIVOS" in cam_upper:
                    emp_especifica = "BG ADESIVOS LTDA"

                eh_entrada = any(
                    t in cam_upper for t in ["ENTRADA", "COMPRA", "FORNECEDOR"]
                )
                registros.append({
                    "Arquivo": nome_arq,
                    "Caminho": item["caminho"],
                    "Mes_Num": 3,
                    "Mês": "03-Mar",
                    "Ano": 2026,
                    "Tipo Operacao": (
                        "Compra (Entrada)" if eh_entrada else "Venda (Saida)"
                    ),
                    "Valor": valor_final,
                    "Empresa": emp_especifica,
                    "Origem": "NFs / Drive",
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
# 3. INTERFACE DO DASHBOARD
# ==========================================
st.title("👑 Executive B.I. — Apuração Fiscal & Conciliação")

df_raw = carregar_ou_gerar_dados()

if not df_raw.empty:
    st.markdown("### 🏢 Empresa:")
    empresas_opcoes = ["TODAS AS EMPRESAS (GRUPO)"] + list(
        EMPRESAS_CONFIG.keys()
    )
    empresa_sel = st.radio(
        "Empresa:",
        empresas_opcoes,
        horizontal=True,
        label_visibility="collapsed",
        key="radio_emp",
    )

    st.markdown("### 📅 Mês:")
    meses_opcoes = ["Consolidado Anual"] + sorted(list(df_raw["Mês"].unique()))
    mes_sel = st.radio(
        "Mês:",
        meses_opcoes,
        horizontal=True,
        label_visibility="collapsed",
        key="radio_mes",
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
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">💰'
            f' FATURAMENTO</div><div'
            f' class="kpi-value">{fmt_moeda(fat_bruto)}</div><div'
            f' class="kpi-sub">{fmt_brl(fat_bruto)}</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="kpi-card" style="border-left: 4px solid'
            ' #2E7D32;"><div class="kpi-title">🛒 COMPRAS</div><div'
            f' class="kpi-value">{fmt_moeda(compras_tot)}</div><div'
            ' class="kpi-sub" style="color:'
            f' #2E7D32;">{fmt_brl(compras_tot)}</div></div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">🏛️ ICMS'
            f' TTS</div><div class="kpi-value">{fmt_moeda(icms)}</div><div'
            ' class="kpi-sub">'
            f'{(icms/fat_bruto*100 if fat_bruto>0 else 0):.2f}% receita</div></div>',
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">📊 PIS /'
            ' COFINS</div><div'
            f' class="kpi-value">{fmt_moeda(piscofins)}</div><div'
            ' class="kpi-sub">3.65% Cumulativo</div></div>',
            unsafe_allow_html=True,
        )
    with c5:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">⚖️ IRPJ /'
            ' CSLL</div><div'
            f' class="kpi-value">{fmt_moeda(irpjcsll)}</div><div'
            ' class="kpi-sub">2.28% Presumido</div></div>',
            unsafe_allow_html=True,
        )
    with c6:
        st.markdown(
            f'<div class="kpi-card" style="border-left: 4px solid'
            ' #D32F2F;"><div class="kpi-title">🚨 TOTAL IMPOSTOS</div><div'
            f' class="kpi-value">{fmt_moeda(tot_impostos)}</div><div'
            ' class="kpi-sub" style="color: #D32F2F;">Carga:'
            f" {aliquota_efetiva:.2f}%</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")
    st.dataframe(
        df_filtrado[[
            "Arquivo",
            "Origem",
            "Mês",
            "Empresa",
            "Tipo Operacao",
            "Valor",
        ]],
        use_container_width=True,
    )
else:
    st.warning("Nenhum dado encontrado ou processado no momento.")
