import io
import re
import xml.etree.ElementTree as ET
import zipfile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
import pandas as pd

try:
    import pypdf

    HAS_PYPDF = True
except ImportError:
    HAS_PYPDF = False

# ==========================================
# 1. CONFIGURAÇÕES COM SEU LINK DO DRIVE
# ==========================================
LINK_OU_ID_DO_DRIVE = "https://drive.google.com/drive/u/2/folders/1s7BomVcbrpDfEMAjOXUNt593VuJ_KOHs"
CREDENTIALS_FILE = "credentials.json"
OUTPUT_FILE = "dados_consolidados.parquet"


def extrair_id_drive(url_ou_id):
    if "folders/" in url_ou_id:
        return url_ou_id.split("folders/")[-1].split("?")[0]
    elif "id=" in url_ou_id:
        return url_ou_id.split("id=")[-1].split("&")[0]
    return url_ou_id.strip()


FOLDER_ID = extrair_id_drive(LINK_OU_ID_DO_DRIVE)

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
    "0745": 1,
    "0746": 2,
    "0747": 3,
    "0748": 4,
    "0749": 5,
    "0750": 6,
    "0751": 7,
    "0752": 8,
    "0753": 9,
    "0754": 10,
    "0755": 11,
    "0756": 12,
}

MESES_NOMES = {
    1: "01-Jan",
    2: "02-Fev",
    3: "03-Mar",
    4: "04-Abr",
    5: "05-Mai",
    6: "06-Jun",
    7: "07-Jul",
    8: "08-Ago",
    9: "09-Set",
    10: "10-Out",
    11: "11-Nov",
    12: "12-Dez",
}


def extrair_valor_xml(bytes_content):
    try:
        root = ET.fromstring(bytes_content)
        for elem in root.iter():
            if "}" in elem.tag:
                elem.tag = elem.tag.split("}", 1)[1]
        v_nf = root.find(".//vNF")
        if v_nf is not None and v_nf.text:
            return float(v_nf.text)
        v_prod = root.find(".//vProd")
        if v_prod is not None and v_prod.text:
            return float(v_prod.text)
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


def extrair_dados_arquivo(bytes_content, caminho_completo):
    registros = []
    nome_arq = caminho_completo.split("/")[-1]
    fn_lower = nome_arq.lower()

    mes_num = 3
    for pasta, m in MAPA_PASTAS_MESES.items():
        if pasta in caminho_completo:
            mes_num = m
            break

    cam_upper = caminho_completo.upper()
    eh_entrada = any(
        t in cam_upper for t in ["ENTRADA", "COMPRA", "FORNECEDOR"]
    )
    tipo_op = "Compra (Entrada)" if eh_entrada else "Venda (Saida)"

    valor_final = 0.0
    if fn_lower.endswith(".xml"):
        valor_final = extrair_valor_xml(bytes_content)
    elif fn_lower.endswith(".pdf"):
        valor_final = extrair_valor_pdf(bytes_content)

    if valor_final <= 0.0:
        return registros

    emp_especifica = "MCRTOTTI LTDA / BRA"
    if "RTX" in cam_upper:
        emp_especifica = "RTX IMPORTS COMERCIAL LTDA"
    elif "BR_TOTTI" in cam_upper or "BW" in cam_upper:
        emp_especifica = "BR TOTTI LTDA / BW"
    elif "BG" in cam_upper or "ADESIVOS" in cam_upper:
        emp_especifica = "BG ADESIVOS LTDA"

    registros.append({
        "Arquivo": nome_arq,
        "Caminho": caminho_completo,
        "Mes_Num": mes_num,
        "Mês": MESES_NOMES.get(mes_num, "03-Mar"),
        "Ano": 2026,
        "Tipo Operacao": tipo_op,
        "Valor": float(valor_final),
        "Empresa": emp_especifica,
        "Origem": "NFs / Drive",
    })
    return registros


def processar_zip(zip_bytes):
    dados = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for info in z.infolist():
                if info.filename.startswith("__MACOSX") or info.is_dir():
                    continue
                if info.filename.lower().endswith((
                    ".pdf",
                    ".xml",
                    ".csv",
                    ".xlsx",
                    ".txt",
                )):
                    try:
                        res = extrair_dados_arquivo(
                            z.read(info), info.filename
                        )
                        if res:
                            dados.extend(res)
                    except Exception:
                        continue
    except Exception:
        pass
    return dados


def executar_consolidacao():
    print("🚀 Conectando ao Google Drive na máquina local...")
    creds = service_account.Credentials.from_service_account_file(
        CREDENTIALS_FILE,
        scopes=["https://www.googleapis.com/auth/drive.readonly"],
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
    print(
        f"📁 Pasta ID [{FOLDER_ID}]: Total de {total} arquivos encontrados no"
        " Drive."
    )

    todos_registros = []
    for idx, item in enumerate(arquivos, start=1):
        print(f"[{idx}/{total}] Processando: {item['nome']}")
        try:
            request = service.files().get_media(fileId=item["id"])
            fh = io.BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            fh.seek(0)
            b = fh.read()

            if item["nome"].lower().endswith(".zip"):
                res = processar_zip(b)
            else:
                res = extrair_dados_arquivo(b, item["caminho"])

            if res:
                todos_registros.extend(res)
        except Exception as e:
            print(f"❌ Erro ao ler {item['nome']}: {e}")

    df_final = pd.DataFrame(todos_registros)
    df_final.to_parquet(OUTPUT_FILE, index=False)
    print(
        f"\n✅ CONSOLIDAÇÃO CONCLUÍDA! Base com {len(df_final)} registros gravada"
        f" em '{OUTPUT_FILE}'."
    )


if __name__ == "__main__":
    executar_consolidacao()
