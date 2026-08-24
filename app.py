import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import os
import gdown
import zipfile

st.set_page_config(page_title="Consolidação Grupo - NFs Google Drive", layout="wide")

st.title("📊 Painel Consolidado — Leitura de NFs do Google Drive")
st.caption("Sincronização direta com a pasta pública de XMLs do Google Drive")

ID_PASTA_DRIVE = "1o9va-LV2UjCDIhasFuw8B_7E-Pef8Q5V"
PASTA_LOCAL = "nfs_download"

# --- FUNÇÃO PARA BAIXAR DA PASTA PÚBLICA DO DRIVE ---
@st.cache_data(ttl=3600)
def baixar_xmls_drive(folder_id):
    if not os.path.exists(PASTA_LOCAL):
        os.makedirs(PASTA_LOCAL)
        
    url_folder = f"https://drive.google.com/drive/folders/{folder_id}"
    try:
        # Baixa o conteúdo da pasta do Drive diretamente
        gdown.download_folder(url_folder, output=PASTA_LOCAL, quiet=True, remaining_ok=True)
        return True
    except Exception as e:
        st.error(f"Erro ao acessar a pasta do Drive: {e}")
        return False

# --- FUNÇÃO PARA EXTRAIR DADOS DOS XMLs ---
def processar_xmls(pasta):
    dados_nfs = []
    
    for root_dir, _, files in os.walk(pasta):
        for file in files:
            if file.endswith('.xml'):
                caminho_xml = os.path.join(root_dir, file)
                try:
                    tree = ET.parse(caminho_xml)
                    root = tree.getroot()
                    ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
                    
                    inf_nfe = root.find('.//nfe:infNFe', ns)
                    if inf_nfe is not None:
                        ide = inf_nfe.find('nfe:ide', ns)
                        emit = inf_nfe.find('nfe:emit', ns)
                        dest = inf_nfe.find('nfe:dest', ns)
                        total = inf_nfe.find('.//nfe:ICMSTot', ns)
                        
                        dt_emissao = ide.find('nfe:dhEmi', ns).text[:10] if ide.find('nfe:dhEmi', ns) is not None else ""
                        raz_emit = emit.find('nfe:xNome', ns).text if emit.find('nfe:xNome', ns) is not None else ""
                        cnpj_emit = emit.find('nfe:CNPJ', ns).text if emit.find('nfe:CNPJ', ns) is not None else ""
                        
                        raz_dest = dest.find('nfe:xNome', ns).text if dest is not None and dest.find('nfe:xNome', ns) is not None else ""
                        v_nf = float(total.find('nfe:vNF', ns).text) if total is not None and total.find('nfe:vNF', ns) is not None else 0.0
                        
                        dados_nfs.append({
                            'Arquivo': file,
                            'CNPJ Emitente': cnpj_emit,
                            'Emitente': raz_emit,
                            'Destinatário': raz_dest,
                            'Data Emissão': dt_emissao,
                            'Valor Total (R$)': v_nf
                        })
                except Exception:
                    pass
    return pd.DataFrame(dados_nfs)

# --- EXECUÇÃO DO FLUXO ---
st.sidebar.header("🔄 Sincronização Drive")
if st.sidebar.button("⚡ Sincronizar com o Google Drive"):
    st.cache_data.clear()
    st.rerun()

with st.spinner("Conectando ao Google Drive e analisando as Notas Fiscais..."):
    sucesso = baixar_xmls_drive(ID_PASTA_DRIVE)

if sucesso:
    df_nfs = processar_xmls(PASTA_LOCAL)
    
    if not df_nfs.empty:
        df_nfs['Data_Parsed'] = pd.to_datetime(df_nfs['Data Emissão'], errors='coerce')
        df_nfs['Ano'] = df_nfs['Data_Parsed'].dt.year
        df_nfs['Mês'] = df_nfs['Data_Parsed'].dt.month
        
        # Filtros Dinâmicos
        st.sidebar.header("📅 Filtro de Período")
        anos_disp = sorted([int(a) for a in df_nfs['Ano'].dropna().unique()])
        ano_sel = st.sidebar.selectbox("Selecione o Ano", anos_disp, index=len(anos_disp)-1 if anos_disp else 0)
        
        meses_dict = {
            1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
            5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
            9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
        }
        mes_sel = st.sidebar.selectbox("Selecione o Mês", list(meses_dict.keys()), format_func=lambda x: meses_dict[x])
        
        # Filtragem
        df_filtrado = df_nfs[(df_nfs['Ano'] == ano_sel) & (df_nfs['Mês'] == mes_sel)]
        
        st.subheader(f"🔄 Resumo de NFs — {meses_dict[mes_sel]}/{ano_sel}")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Valor Total das NFs no Mês", f"R$ {df_filtrado['Valor Total (R$)'].sum():,.2f}")
        c2.metric("Qtd. de NFs no Mês", len(df_filtrado))
        c3.metric("Total de XMLs na Pasta", len(df_nfs))
        
        st.markdown("---")
        st.dataframe(df_filtrado[['Arquivo', 'Data Emissão', 'Emitente', 'Destinatário', 'Valor Total (R$)']], use_container_width=True)
    else:
        st.warning("A pasta do Google Drive foi acessada, mas nenhum arquivo XML válido foi encontrado dentro dela.")
