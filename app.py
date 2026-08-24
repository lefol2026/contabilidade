import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import zipfile
import io

st.set_page_config(page_title="Consolidação Grupo - Leitor de NFs", layout="wide")

st.title("📊 Painel Consolidado do Grupo — Leitura de Notas Fiscais")
st.caption("Faça o upload do arquivo .ZIP de cada empresa para consolidar os dados")

# --- BARRA LATERAL: UPLOAD E FILTROS ---
st.sidebar.header("📁 Importar Arquivos")

arquivos_subidos = st.sidebar.file_uploader(
    "Suba os arquivos .ZIP ou .XML aqui", 
    type=["zip", "xml"], 
    accept_multiple_files=True
)

st.sidebar.markdown("---")

dados_nfs = []

# --- PROCESSAMENTO DOS ARQUIVOS ---
if arquivos_subidos:
    for arq in arquivos_subidos:
        # Processamento de arquivos ZIP
        if arq.name.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(arq) as z:
                    for filename in z.namelist():
                        if filename.lower().endswith('.xml'):
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

        # Processamento de XMLs soltos
        elif arq.name.lower().endswith('.xml'):
            try:
                tree = ET.parse(arq)
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
                        'Arquivo': arq.name,
                        'Empresa Origem': arq.name,
                        'CNPJ Emitente': cnpj_emit,
                        'Emitente': raz_emit,
                        'Destinatário': raz_dest,
                        'Data Emissão': dt_emissao,
                        'Valor Total (R$)': v_nf
                    })
            except Exception:
                pass

# --- EXIBIÇÃO DOS RESULTADOS ---
if dados_nfs:
    df_nfs = pd.DataFrame(dados_nfs)
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
    
    # Resumo por Emitente/Empresa
    if not df_filtrado.empty:
        st.subheader("🏢 Faturamento por Emitente no Mês")
        resumo_emit = df_filtrado.groupby('Emitente')['Valor Total (R$)'].sum().reset_index()
        resumo_emit['Valor Total (R$)'] = resumo_emit['Valor Total (R$)'].map("R$ {:,.2f}".format)
        st.table(resumo_emit)
    
    st.subheader("📋 Lista Detalhada das Notas Fiscais")
    st.dataframe(df_filtrado[['Arquivo', 'Data Emissão', 'Emitente', 'Destinatário', 'Valor Total (R$)']], use_container_width=True)

else:
    st.info("👈 Acesse o menu lateral na esquerda e faça o upload do arquivo `.zip` da RTX para testar.")
