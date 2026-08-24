import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import zipfile
import io

st.set_page_config(page_title="Consolidação Grupo - Leitor Universal", layout="wide")

st.title("📊 Painel Consolidado do Grupo — Leitura de NFs e Relatórios")
st.caption("Suporte para XMLs de NFs, arquivos ZIPs aninhados e planilhas Excel")

# --- BARRA LATERAL: UPLOAD E PROCESSAMENTO ---
st.sidebar.header("📁 Importar Arquivos")

arquivos_subidos = st.sidebar.file_uploader(
    "Suba o arquivo .ZIP baixado do Google Drive", 
    type=["zip", "xml", "xls", "xlsx"], 
    accept_multiple_files=True
)

st.sidebar.markdown("---")
btn_processar = st.sidebar.button("🚀 Processar Arquivos", type="primary")

def extrair_dados_xml(xml_content, nome_arquivo):
    try:
        tree = ET.parse(io.BytesIO(xml_content))
        root = tree.getroot()
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        
        inf_nfe = root.find('.//nfe:infNFe', ns)
        if inf_nfe is not None:
            ide = inf_nfe.find('nfe:ide', ns)
            emit = inf_nfe.find('nfe:emit', ns)
            dest = inf_nfe.find('nfe:dest', ns)
            total = inf_nfe.find('.//nfe:ICMSTot', ns)
            
            dt_emissao = ide.find('nfe:dhEmi', ns).text[:10] if (ide is not None and ide.find('nfe:dhEmi', ns) is not None) else ""
            raz_emit = emit.find('nfe:xNome', ns).text if (emit is not None and emit.find('nfe:xNome', ns) is not None) else "Desconhecido"
            cnpj_emit = emit.find('nfe:CNPJ', ns).text if (emit is not None and emit.find('nfe:CNPJ', ns) is not None) else ""
            
            raz_dest = dest.find('nfe:xNome', ns).text if (dest is not None and dest.find('nfe:xNome', ns) is not None) else "Consumidor Final"
            v_nf = float(total.find('nfe:vNF', ns).text) if (total is not None and total.find('nfe:vNF', ns) is not None) else 0.0
            
            return {
                'Arquivo': nome_arquivo,
                'CNPJ Emitente': cnpj_emit,
                'Emitente': raz_emit,
                'Destinatário': raz_dest,
                'Data Emissão': dt_emissao,
                'Valor Total (R$)': v_nf
            }
    except Exception:
        pass
    return None

def ler_zip_recursivo(zip_bytes, nome_origem):
    dados = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for filename in z.namelist():
                if filename.startswith('__MACOSX'):
                    continue
                
                # Se encontrar um ZIP dentro do ZIP
                if filename.lower().endswith('.zip'):
                    sub_zip_bytes = z.read(filename)
                    dados.extend(ler_zip_recursivo(sub_zip_bytes, filename))
                
                # Se encontrar um XML
                elif filename.lower().endswith('.xml'):
                    content = z.read(filename)
                    res = extrair_dados_xml(content, filename.split('/')[-1])
                    if res:
                        dados.append(res)
    except Exception:
        pass
    return dados

# --- PROCESSAMENTO ---
if btn_processar and arquivos_subidos:
    dados_nfs = []
    
    with st.spinner("Varrendo pastas, descompactando ZIPs internos e analisando XMLs..."):
        for arq in arquivos_subidos:
            if arq.name.lower().endswith('.zip'):
                dados_nfs.extend(ler_zip_recursivo(arq.read(), arq.name))
            elif arq.name.lower().endswith('.xml'):
                res = extrair_dados_xml(arq.read(), arq.name)
                if res:
                    dados_nfs.append(res)

    if dados_nfs:
        st.session_state['df_nfs'] = pd.DataFrame(dados_nfs)
        st.success(f"✅ Processamento concluído! {len(dados_nfs)} Notas Fiscais em XML foram identificadas e consolidadas.")
    else:
        st.warning("⚠️ O ZIP foi analisado, mas não continha XMLs de NF-e válidos. (Arquivos PDF e EML foram ignorados).")

# --- VISUALIZAÇÃO ---
if 'df_nfs' in st.session_state:
    df_nfs = st.session_state['df_nfs']
    df_nfs['Data_Parsed'] = pd.to_datetime(df_nfs['Data Emissão'], errors='coerce')
    df_nfs['Ano'] = df_nfs['Data_Parsed'].dt.year
    df_nfs['Mês'] = df_nfs['Data_Parsed'].dt.month
    
    st.sidebar.header("📅 Filtro de Período")
    
    anos_disp = sorted([int(a) for a in df_nfs['Ano'].dropna().unique()])
    ano_sel = st.sidebar.selectbox("Selecione o Ano", anos_disp, index=len(anos_disp)-1 if anos_disp else 0)
    
    meses_dict = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    mes_sel = st.sidebar.selectbox("Selecione o Mês", list(meses_dict.keys()), format_func=lambda x: meses_dict[x])
    
    df_filtrado = df_nfs[(df_nfs['Ano'] == ano_sel) & (df_nfs['Mês'] == mes_sel)]
    
    st.subheader(f"🔄 Faturamento Consolidado — {meses_dict[mes_sel]}/{ano_sel}")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Valor Total faturado no Mês", f"R$ {df_filtrado['Valor Total (R$)'].sum():,.2f}")
    c2.metric("NFs no Mês", len(df_filtrado))
    c3.metric("Total Geral de XMLs Encontrados", len(df_nfs))
    
    st.markdown("---")
    
    if not df_filtrado.empty:
        st.subheader("🏢 Consolidado por Empresa Emitente")
        resumo = df_filtrado.groupby('Emitente')['Valor Total (R$)'].sum().reset_index()
        resumo['Valor Total (R$)'] = resumo['Valor Total (R$)'].map("R$ {:,.2f}".format)
        st.table(resumo)
    
    st.subheader("📋 Lista de Notas Fiscais Processadas")
    st.dataframe(df_filtrado[['Arquivo', 'Data Emissão', 'Emitente', 'Destinatário', 'Valor Total (R$)']], use_container_width=True)

elif not btn_processar:
    st.info("👈 Envie o arquivo `.zip` da RTX no menu lateral e clique em **🚀 Processar Arquivos**.")
