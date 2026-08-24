import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import zipfile
import io

st.set_page_config(page_title="Consolidação Grupo - Leitor de NFs", layout="wide")

st.title("📊 Painel Consolidado do Grupo — Leitura de Notas Fiscais")
st.caption("Processamento automático de arquivos ZIP com suporte a subpastas")

# --- BARRA LATERAL: UPLOAD E BOTÃO DE PROCESSAMENTO ---
st.sidebar.header("📁 Importar Arquivos")

arquivos_subidos = st.sidebar.file_uploader(
    "Suba os arquivos .ZIP ou .XML aqui", 
    type=["zip", "xml"], 
    accept_multiple_files=True
)

st.sidebar.markdown("---")
btn_processar = st.sidebar.button("🚀 Processar Notas Fiscais", type="primary")

# --- PROCESSAMENTO DOS ARQUIVOS ---
if btn_processar and arquivos_subidos:
    dados_nfs = []
    
    with st.spinner("Analisando e extraindo dados do arquivo ZIP... Aguarde!"):
        for arq in arquivos_subidos:
            if arq.name.lower().endswith('.zip'):
                try:
                    with zipfile.ZipFile(arq) as z:
                        for filename in z.namelist():
                            # Procura arquivos .xml em qualquer subpasta interna do ZIP
                            if filename.lower().endswith('.xml') and not filename.startswith('__MACOSX'):
                                try:
                                    content = z.read(filename)
                                    tree = ET.parse(io.BytesIO(content))
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
                                        
                                        dados_nfs.append({
                                            'Arquivo': filename.split('/')[-1],
                                            'Empresa Origem': arq.name,
                                            'CNPJ Emitente': cnpj_emit,
                                            'Emitente': raz_emit,
                                            'Destinatário': raz_dest,
                                            'Data Emissão': dt_emissao,
                                            'Valor Total (R$)': v_nf
                                        })
                                except Exception:
                                    pass
                except Exception as e:
                    st.sidebar.error(f"Erro ao abrir {arq.name}: {e}")

    if dados_nfs:
        st.session_state['df_nfs'] = pd.DataFrame(dados_nfs)
        st.success(f"✅ Sucesso! {len(dados_nfs)} notas fiscais foram lidas e processadas.")
    else:
        st.warning("⚠️ Nenhum arquivo .XML de NF-e válido foi encontrado dentro do arquivo .ZIP enviado.")

# --- EXIBIÇÃO DOS RESULTADOS GUARDADOS EM SESSÃO ---
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
    
    # Filtragem
    df_filtrado = df_nfs[(df_nfs['Ano'] == ano_sel) & (df_nfs['Mês'] == mes_sel)]
    
    st.subheader(f"🔄 Resumo de Faturamento das NFs — {meses_dict[mes_sel]}/{ano_sel}")
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Valor Total das NFs no Mês", f"R$ {df_filtrado['Valor Total (R$)'].sum():,.2f}")
    c2.metric("Qtd. de NFs no Mês", len(df_filtrado))
    c3.metric("Total de XMLs Analisados", len(df_nfs))
    
    st.markdown("---")
    
    if not df_filtrado.empty:
        st.subheader("🏢 Faturamento por Emitente no Mês")
        resumo_emit = df_filtrado.groupby('Emitente')['Valor Total (R$)'].sum().reset_index()
        resumo_emit['Valor Total (R$)'] = resumo_emit['Valor Total (R$)'].map("R$ {:,.2f}".format)
        st.table(resumo_emit)
    
    st.subheader("📋 Lista Detalhada das Notas Fiscais")
    st.dataframe(df_filtrado[['Arquivo', 'Data Emissão', 'Emitente', 'Destinatário', 'Valor Total (R$)']], use_container_width=True)

elif not btn_processar:
    st.info("👈 O arquivo `.zip` da RTX foi carregado na barra lateral! Clique no botão **🚀 Processar Notas Fiscais** para gerar o painel.")
