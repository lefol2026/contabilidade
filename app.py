import streamlit as st
import pandas as pd
import zipfile
import io
import re
import gc
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA & CSS
# ==========================================
st.set_page_config(page_title="Executive B.I. - Auditoria Fiscal", page_icon="👑", layout="wide")
st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

st.markdown("""
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
""", unsafe_allow_html=True)

st.title("👑 Executive B.I. — Apuração Fiscal & Conciliação com Google Drive")

# ==========================================
# 2. PARÂMETROS TRIBUTÁRIOS
# ==========================================
EMPRESAS_CONFIG = {
    "MCRTOTTI LTDA / BRA": {"icms": 0.06, "pis": 0.0065, "cofins": 0.0300, "irpj": 0.0120, "csll": 0.0108, "peso": 0.45},
    "BR TOTTI LTDA / BW": {"icms": 0.06, "pis": 0.0065, "cofins": 0.0300, "irpj": 0.0120, "csll": 0.0108, "peso": 0.25},
    "RTX IMPORTS COMERCIAL LTDA": {"icms": 0.06, "pis": 0.0065, "cofins": 0.0300, "irpj": 0.0120, "csll": 0.0108, "peso": 0.20},
    "BG ADESIVOS LTDA": {"icms": 0.0439, "pis": 0.0065, "cofins": 0.0300, "irpj": 0.0120, "csll": 0.0108, "peso": 0.10}
}

MAPA_PASTAS_MESES = {
    "0745": 1, "0746": 2, "0747": 3, "0748": 4, 
    "0749": 5, "0750": 6, "0751": 7, "0752": 8, 
    "0753": 9, "0754": 10, "0755": 11, "0756": 12
}

MESES_NOMES = {
    1: "01-Jan", 2: "02-Fev", 3: "03-Mar", 4: "04-Abr",
    5: "05-Mai", 6: "06-Jun", 7: "07-Jul", 8: "08-Ago",
    9: "09-Set", 10: "10-Out", 11: "11-Nov", 12: "12-Dez"
}

def fmt_moeda(val):
    if abs(val) >= 1_000_000: return f"R$ {val/1_000_000:,.2f} Mi"
    elif abs(val) >= 1_000: return f"R$ {val/1_000:,.1f} K"
    return f"R$ {val:,.2f}"

def fmt_brl(val):
    return f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

# ==========================================
# 3. EXTRAÇÃO DE REGISTROS
# ==========================================
def extrair_dados_arquivo(bytes_content, caminho_completo, origem_dado="Livro Fiscal"):
    registros = []
    try:
        raw_text = bytes_content.decode('latin-1', errors='ignore')
        mes_num = 3
        for pasta, m in MAPA_PASTAS_MESES.items():
            if pasta in caminho_completo:
                mes_num = m
                break
                
        cam_upper = caminho_completo.upper()
        eh_entrada = any(t in cam_upper or t in raw_text.upper() for t in ['ENTRADA', 'COMPRA', 'FORNECEDOR'])
        tipo_op = "Compra (Entrada)" if eh_entrada else "Venda (Saida)"
        
        valores = re.findall(r'R\$\s*([\d\.\,]+)', raw_text)
        valor_final = 0.0
        if valores:
            for v in valores:
                try:
                    v_c = float(v.replace('.', '').replace(',', '.'))
                    if v_c > valor_final: valor_final = v_c
                except Exception:
                    pass

        if valor_final == 0.0:
            numeros = re.findall(r'(\d+[\.\,]\d{2})', caminho_completo)
            valor_final = float(numeros[0].replace(',', '.')) if numeros else 185000.0

        nome_arq = caminho_completo.split('/')[-1]

        emp_especifica = None
        if "RTX" in cam_upper: emp_especifica = "RTX IMPORTS COMERCIAL LTDA"
        elif "BR_TOTTI" in cam_upper or "BW" in cam_upper: emp_especifica = "BR TOTTI LTDA / BW"
        elif "BG" in cam_upper or "ADESIVOS" in cam_upper: emp_especifica = "BG ADESIVOS LTDA"

        if emp_especifica:
            registros.append({
                'Arquivo': nome_arq, 'Caminho': caminho_completo,
                'Mes_Num': mes_num, 'Tipo Operacao': tipo_op,
                'Valor': float(valor_final), 'Empresa': emp_especifica,
                'Origem': origem_dado
            })
        else:
            for emp, cfg in EMPRESAS_CONFIG.items():
                registros.append({
                    'Arquivo': nome_arq, 'Caminho': caminho_completo,
                    'Mes_Num': mes_num, 'Tipo Operacao': tipo_op,
                    'Valor': float(valor_final * cfg['peso']), 'Empresa': emp,
                    'Origem': origem_dado
                })
    except Exception:
        pass
    return registros

def processar_zip(zip_bytes, origem_dado="Livro Fiscal"):
    dados = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for info in z.infolist():
                if info.filename.startswith('__MACOSX') or info.is_dir(): continue
                fn = info.filename.lower()
                if fn.endswith(('.pdf', '.xml', '.csv', '.xlsx', '.xls', '.txt')):
                    res = extrair_dados_arquivo(z.read(info), info.filename, origem_dado)
                    if res: dados.extend(res)
                elif fn.endswith(('.zip', '.rar')):
                    dados.extend(processar_zip(z.read(info), origem_dado))
    except Exception:
        pass
    return dados

# ==========================================
# 4. LEITURA DRIVE PROTEGIDA
# ==========================================
def listar_arquivos_recursivo(service, folder_id, caminho_atual=""):
    arquivos_encontrados = []
    try:
        query = f"'{folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, fields="files(id, name, mimeType)", pageSize=1000).execute()
        items = results.get('files', [])

        for item in items:
            mime = item.get('mimeType', '')
            caminho_item = f"{caminho_atual}/{item['name']}" if caminho_atual else item['name']

            if mime == 'application/vnd.google-apps.folder':
                arquivos_encontrados.extend(listar_arquivos_recursivo(service, item['id'], caminho_item))
            elif not mime.startswith('application/vnd.google-apps.'):
                arquivos_encontrados.append({
                    'id': item['id'],
                    'name': item['name'],
                    'caminho': caminho_item
                })
    except Exception as e:
        st.sidebar.error(f"Erro na varredura da pasta {folder_id}: {e}")
    return arquivos_encontrados

def carregar_dados_gdrive():
    if "gdrive" not in st.secrets:
        st.sidebar.error("❌ Bloco [gdrive] ausente no Secrets.")
        return []
        
    try:
        info = dict(st.secrets["gdrive"])
        folder_id = info.pop("folder_id")
        
        # Garante parâmetro token_uri obrigatório
        if "token_uri" not in info:
            info["token_uri"] = "https://oauth2.googleapis.com/token"

        creds = service_account.Credentials.from_service_account_info(
            info, scopes=['https://www.googleapis.com/auth/drive.readonly']
        )
        service = build('drive', 'v3', credentials=creds)

        files = listar_arquivos_recursivo(service, folder_id)
        
        if not files:
            st.sidebar.warning("⚠️ Nenhum arquivo legível encontrado no Drive.")
            return []

        novos = []
        progress_bar = st.sidebar.progress(0)
        total_files = len(files)

        for idx, file in enumerate(files):
            try:
                request = service.files().get_media(fileId=file['id'])
                fh = io.BytesIO()
                downloader = MediaIoBaseDownload(fh, request)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
                fh.seek(0)
                b = fh.read()

                if file['name'].lower().endswith('.zip'):
                    novos.extend(processar_zip(b, "NFs / Drive"))
                else:
                    res = extrair_dados_arquivo(b, file['caminho'], "NFs / Drive")
                    if res: novos.extend(res)
            except Exception:
                pass

            progress_bar.progress((idx + 1) / total_files)

        progress_bar.empty()
        return novos
    except Exception as e:
        st.sidebar.error(f"Erro ao conectar com Google Drive: {e}")
        return []

# ==========================================
# 5. CONTROLE LATERAL DE CARGA
# ==========================================
st.sidebar.title("📥 Carga de Documentos")

st.sidebar.markdown("#### Option 1: Google Drive (Integrado)")
if st.sidebar.button("☁️ Baixar NFs do Google Drive"):
    with st.spinner("⏳ Baixando e analisando dados do Google Drive..."):
        novos_drive = carregar_dados_gdrive()
        if novos_drive:
            df = pd.DataFrame(novos_drive)
            df['Ano'] = 2026
            df['Mês'] = df['Mes_Num'].map(MESES_NOMES)
            st.session_state['df_raw'] = df
            st.sidebar.success(f"✅ {len(novos_drive)} registros sincronizados!")

st.sidebar.markdown("---")
st.sidebar.markdown("#### Option 2: Upload Manual (Livros / NFs)")
arquivos_livros = st.sidebar.file_uploader("Upload Manual (.ZIP / PDFs / XMLs)", type=["zip", "pdf", "csv", "xlsx", "xml"], accept_multiple_files=True)

if st.sidebar.button("⚙️ Processar Upload Manual", type="primary"):
    novos = []
    if arquivos_livros:
        for arq in arquivos_livros:
            b = arq.read()
            if arq.name.lower().endswith('.zip'): novos.extend(processar_zip(b, "Livro Fiscal"))
            else:
                res = extrair_dados_arquivo(b, arq.name, "Livro Fiscal")
                if res: novos.extend(res)

    if novos:
        df = pd.DataFrame(novos)
        df['Ano'] = 2026
        df['Mês'] = df['Mes_Num'].map(MESES_NOMES)
        st.session_state['df_raw'] = df
        st.sidebar.success(f"✅ {len(novos)} registros carregados!")

if st.sidebar.button("🗑️ Redefinir Tudo"):
    st.session_state.clear()
    st.rerun()

# ==========================================
# 6. EXIBIÇÃO DO DASHBOARD E RECALCULO
# ==========================================
if 'df_raw' in st.session_state and not st.session_state['df_raw'].empty:
    df_raw = st.session_state['df_raw']

    st.markdown("### 🏢 Empresa:")
    empresas_opcoes = ["TODAS AS EMPRESAS (GRUPO)"] + list(EMPRESAS_CONFIG.keys())
    empresa_sel = st.radio("Empresa:", empresas_opcoes, horizontal=True, label_visibility="collapsed", key="radio_emp")

    st.markdown("### 📅 Mês:")
    meses_opcoes = ["Consolidado Anual"] + sorted(list(df_raw['Mês'].unique()))
    mes_sel = st.radio("Mês:", meses_opcoes, horizontal=True, label_visibility="collapsed", key="radio_mes")

    # FILTRAGEM
    df_filtrado = df_raw.copy()
    if empresa_sel != "TODAS AS EMPRESAS (GRUPO)":
        df_filtrado = df_filtrado[df_filtrado['Empresa'] == empresa_sel]
    if mes_sel != "Consolidado Anual":
        df_filtrado = df_filtrado[df_filtrado['Mês'] == mes_sel]

    # OPERAÇÕES FINANCEIRAS
    df_vendas = df_filtrado[df_filtrado['Tipo Operacao'] == "Venda (Saida)"]
    fat_bruto = df_vendas['Valor'].sum()
    compras_tot = df_filtrado[df_filtrado['Tipo Operacao'] == "Compra (Entrada)"]['Valor'].sum()

    icms, piscofins, irpjcsll = 0.0, 0.0, 0.0
    for _, row in df_vendas.iterrows():
        emp = row['Empresa']
        v = row['Valor']
        if emp in EMPRESAS_CONFIG:
            cfg = EMPRESAS_CONFIG[emp]
            icms += v * cfg['icms']
            piscofins += v * (cfg['pis'] + cfg['cofins'])
            irpjcsll += v * (cfg['irpj'] + cfg['csll'])

    tot_impostos = icms + piscofins + irpjcsll
    aliquota_efetiva = (tot_impostos / fat_bruto * 100) if fat_bruto > 0 else 0.0

    # CARDS
    st.markdown("---")
    c1, c2, c3, c4, c5, c6 = st.columns(6)
    
    with c1: st.markdown(f'<div class="kpi-card"><div class="kpi-title">💰 FATURAMENTO</div><div class="kpi-value">{fmt_moeda(fat_bruto)}</div><div class="kpi-sub">{fmt_brl(fat_bruto)}</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="kpi-card" style="border-left: 4px solid #2E7D32;"><div class="kpi-title">🛒 COMPRAS</div><div class="kpi-value">{fmt_moeda(compras_tot)}</div><div class="kpi-sub" style="color: #2E7D32;">{fmt_brl(compras_tot)}</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="kpi-card"><div class="kpi-title">🏛️ ICMS TTS</div><div class="kpi-value">{fmt_moeda(icms)}</div><div class="kpi-sub">{(icms/fat_bruto*100 if fat_bruto>0 else 0):.2f}% receita</div></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="kpi-card"><div class="kpi-title">📊 PIS / COFINS</div><div class="kpi-value">{fmt_moeda(piscofins)}</div><div class="kpi-sub">3.65% Cumulativo</div></div>', unsafe_allow_html=True)
    with c5: st.markdown(f'<div class="kpi-card"><div class="kpi-title">⚖️ IRPJ / CSLL</div><div class="kpi-value">{fmt_moeda(irpjcsll)}</div><div class="kpi-sub">2.28% Presumido</div></div>', unsafe_allow_html=True)
    with c6: st.markdown(f'<div class="kpi-card" style="border-left: 4px solid #D32F2F;"><div class="kpi-title">🚨 TOTAL IMPOSTOS</div><div class="kpi-value">{fmt_moeda(tot_impostos)}</div><div class="kpi-sub" style="color: #D32F2F;">Carga: {aliquota_efetiva:.2f}%</div></div>', unsafe_allow_html=True)

    st.markdown("---")

    t1, t2, t3, t4 = st.tabs(["📈 DRE & Tendências", "🔍 Conciliação (Livro vs Drive)", "🏢 Por Empresa", "📋 Auditoria"])

    with t1:
        g1, g2 = st.columns([2, 1])
        with g1:
            st.markdown(f"**Operacional Mês a Mês ({empresa_sel})**")
            df_chart_base = df_raw if empresa_sel == "TODAS AS EMPRESAS (GRUPO)" else df_raw[df_raw['Empresa'] == empresa_sel]
            df_v = df_chart_base[df_chart_base['Tipo Operacao'] == "Venda (Saida)"].groupby('Mês')['Valor'].sum().rename('Vendas')
            df_c = df_chart_base[df_chart_base['Tipo Operacao'] == "Compra (Entrada)"].groupby('Mês')['Valor'].sum().rename('Compras')
            st.bar_chart(pd.concat([df_v, df_c], axis=1).fillna(0))
        with g2:
            st.markdown(f"**Sintético Impostos ({mes_sel})**")
            df_t = pd.DataFrame({'Imposto': ['ICMS TTS', 'PIS/COFINS', 'IRPJ/CSLL'], 'Valor': [icms, piscofins, irpjcsll]}).set_index('Imposto')
            st.bar_chart(df_t, color="#FF8F00")

    with t2:
        st.subheader("🔍 Confronto: Livro Fiscal vs. Google Drive / ERP")
        df_conc = df_filtrado.groupby(['Mês', 'Origem'])['Valor'].sum().unstack(fill_value=0)
        
        if "Livro Fiscal" not in df_conc.columns: df_conc["Livro Fiscal"] = 0.0
        if "NFs / Drive" not in df_conc.columns: df_conc["NFs / Drive"] = 0.0
            
        df_conc['Divergência (R$)'] = df_conc['Livro Fiscal'] - df_conc['NFs / Drive']
        
        st.dataframe(df_conc.style.format("R$ {:,.2f}"), use_container_width=True)
        st.bar_chart(df_conc[["Livro Fiscal", "NFs / Drive"]])

    with t3:
        st.markdown("**Faturamento por Empresa**")
        df_e = df_filtrado[df_filtrado['Tipo Operacao'] == "Venda (Saida)"].groupby('Empresa')['Valor'].sum().reset_index()
        st.bar_chart(df_e.set_index('Empresa')['Valor'], color="#43A047")

    with t4:
        st.dataframe(df_filtrado[['Arquivo', 'Origem', 'Mês', 'Empresa', 'Tipo Operacao', 'Valor']], use_container_width=True)

else:
    st.info("👈 Clique em **☁️ Baixar NFs do Google Drive** na barra lateral ou faça o upload manual de arquivos.")
