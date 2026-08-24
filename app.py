import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import zipfile
import io

st.set_page_config(page_title="Consolidação Grupo - Painel Fiscal & Anual", layout="wide")

st.title("📊 Painel Consolidado do Grupo — Vendas, Compras & Fiscal")
st.caption("Consolidação Inteligente via XMLs: Visão Mensal, Anual e Apuração de Impostos")

# --- CNPJs E ALÍQUOTAS DO GRUPO ---
EMPRESAS_CONFIG = {
    "RTX IMPORTS COMERCIAL LTDA": {"cnpj": "55175101000195", "aliq": 0.06, "regime": "Lucro Presumido / TTS MG"},
    "M C R TOTTI LTDA (BRA)": {"cnpj": "05221508000128", "aliq": 0.1132, "regime": "Lucro Presumido"},
    "BG ADESIVOS LTDA": {"cnpj": "05221462000124", "aliq": 0.1132, "regime": "Lucro Presumido"},
    "B R TOTTI LTDA (BW)": {"cnpj": "05221508000209", "aliq": 0.1132, "regime": "Lucro Presumido"}
}

# Lista de CNPJs cadastrados para rápida checagem
CNPJS_GRUPO = [v["cnpj"] for v in EMPRESAS_CONFIG.values()]

# --- BARRA LATERAL: UPLOAD E BOTÃO ---
st.sidebar.header("📁 Importar Arquivos")
arquivos_subidos = st.sidebar.file_uploader(
    "Suba o arquivo .ZIP baixado do Google Drive", 
    type=["zip", "xml"], 
    accept_multiple_files=True
)

st.sidebar.markdown("---")
btn_processar = st.sidebar.button("🚀 Processar Notas Fiscais", type="primary")

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
            cnpj_dest = dest.find('nfe:CNPJ', ns).text if (dest is not None and dest.find('nfe:CNPJ', ns) is not None) else ""
            
            v_nf = float(total.find('nfe:vNF', ns).text) if (total is not None and total.find('nfe:vNF', ns) is not None) else 0.0
            
            # Identifica se é Venda ou Compra
            cnpj_emit_limpo = cnpj_emit.replace(".", "").replace("/", "").replace("-", "").strip()
            tipo_operacao = "Venda (Saída)" if cnpj_emit_limpo in CNPJS_GRUPO else "Compra (Entrada)"
            
            return {
                'Arquivo': nome_arquivo,
                'Tipo Operação': tipo_operacao,
                'CNPJ Emitente': cnpj_emit,
                'Emitente': raz_emit,
                'CNPJ Destinatário': cnpj_dest,
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
                if filename.lower().endswith('.zip'):
                    sub_zip_bytes = z.read(filename)
                    dados.extend(ler_zip_recursivo(sub_zip_bytes, filename))
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
    with st.spinner("Analisando notas fiscais, operacoes de venda e compra..."):
        for arq in arquivos_subidos:
            if arq.name.lower().endswith('.zip'):
                dados_nfs.extend(ler_zip_recursivo(arq.read(), arq.name))
            elif arq.name.lower().endswith('.xml'):
                res = extrair_dados_xml(arq.read(), arq.name)
                if res:
                    dados_nfs.append(res)

    if dados_nfs:
        st.session_state['df_nfs'] = pd.DataFrame(dados_nfs)
        st.success(f"✅ Sucesso! {len(dados_nfs)} notas fiscais foram lidas e classificadas.")
    else:
        st.warning("⚠️ Nenhum arquivo XML válido foi encontrado no pacote enviado.")

# --- EXIBIÇÃO E EXPORTAÇÃO ---
if 'df_nfs' in st.session_state:
    df_nfs = st.session_state['df_nfs']
    df_nfs['Data_Parsed'] = pd.to_datetime(df_nfs['Data Emissão'], errors='coerce')
    df_nfs['Ano'] = df_nfs['Data_Parsed'].dt.year
    df_nfs['Mês'] = df_nfs['Data_Parsed'].dt.month
    
    anos_disp = sorted([int(a) for a in df_nfs['Ano'].dropna().unique()])
    
    st.sidebar.header("📅 Filtro de Período")
    ano_sel = st.sidebar.selectbox("Selecione o Ano", anos_disp, index=len(anos_disp)-1 if anos_disp else 0)
    
    meses_dict = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    mes_sel = st.sidebar.selectbox("Selecione o Mês", list(meses_dict.keys()), format_func=lambda x: meses_dict[x])

    tab1, tab2, tab3 = st.tabs(["📅 Visão Mensal", "📊 Resumo Anual", "📑 Apuração Fiscal & Comparativo"])

    # --- TAB 1: VISÃO MENSAL ---
    with tab1:
        df_mes = df_nfs[(df_nfs['Ano'] == ano_sel) & (df_nfs['Mês'] == mes_sel)]
        
        vendas_mes = df_mes[df_mes['Tipo Operação'] == "Venda (Saída)"]['Valor Total (R$)'].sum()
        compras_mes = df_mes[df_mes['Tipo Operação'] == "Compra (Entrada)"]['Valor Total (R$)'].sum()
        resultado_mes = vendas_mes - compras_mes
        
        # Cálculo do Imposto Estimado (Soma das alíquotas pelas vendas por emitente)
        imposto_mes = 0.0
        for emp_nome, emp_info in EMPRESAS_CONFIG.items():
            sub_vendas = df_mes[(df_mes['Tipo Operação'] == "Venda (Saída)") & (df_mes['Emitente'].str.contains(emp_nome.split()[0], case=False, na=False))]['Valor Total (R$)'].sum()
            imposto_mes += sub_vendas * emp_info['aliq']

        st.subheader(f"🔄 Balanço Mensal — {meses_dict[mes_sel]}/{ano_sel}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Vendas Totais (Saídas)", f"R$ {vendas_mes:,.2f}")
        c2.metric("Compras Totais (Entradas)", f"R$ {compras_mes:,.2f}")
        c3.metric("Resultado Bruto", f"R$ {resultado_mes:,.2f}")
        c4.metric("Imposto Estimado (Vendas)", f"R$ {imposto_mes:,.2f}")

        st.markdown("---")
        st.subheader("📋 Detalhamento das Notas do Mês")
        st.dataframe(df_mes[['Arquivo', 'Tipo Operação', 'Data Emissão', 'Emitente', 'Destinatário', 'Valor Total (R$)']], use_container_width=True)

    # --- TAB 2: RESUMO ANUAL ---
    with tab2:
        st.subheader(f"📊 Consolidado Mês a Mês — Ano {ano_sel}")
        df_ano = df_nfs[df_nfs['Ano'] == ano_sel]
        
        resumo_anual = []
        for m_num, m_nome in meses_dict.items():
            df_m = df_ano[df_ano['Mês'] == m_num]
            v_vendas = df_m[df_m['Tipo Operação'] == "Venda (Saída)"]['Valor Total (R$)'].sum()
            v_compras = df_m[df_m['Tipo Operação'] == "Compra (Entrada)"]['Valor Total (R$)'].sum()
            
            resumo_anual.append({
                "Mês": m_nome,
                "Vendas (Saídas)": f"R$ {v_vendas:,.2f}",
                "Compras (Entradas)": f"R$ {v_compras:,.2f}",
                "Resultado Operacional": f"R$ {(v_vendas - v_compras):,.2f}"
            })
            
        st.table(pd.DataFrame(resumo_anual))

    # --- TAB 3: APURAÇÃO FISCAL E COMPARAÇÃO ---
    with tab3:
        st.subheader(f"📑 Apuração de Impostos por Empresa — {meses_dict[mes_sel]}/{ano_sel}")
        
        relatorio_fiscal = []
        df_mes = df_nfs[(df_nfs['Ano'] == ano_sel) & (df_nfs['Mês'] == mes_sel)]
        
        for emp_nome, emp_info in EMPRESAS_CONFIG.items():
            # Busca notas emitidas por esta empresa
            sub_vendas = df_mes[(df_mes['Tipo Operação'] == "Venda (Saída)") & (df_mes['Emitente'].str.contains(emp_nome.split()[0], case=False, na=False))]['Valor Total (R$)'].sum()
            imposto_apurado = sub_vendas * emp_info['aliq']
            
            relatorio_fiscal.append({
                "Empresa": emp_nome,
                "Regime Fiscal": emp_info['regime'],
                "Faturamento (Vendas)": f"R$ {sub_vendas:,.2f}",
                "Alíquota Est.": f"{emp_info['aliq']*100:.2f}%",
                "Imposto Apurado (Devido)": f"R$ {imposto_apurado:,.2f}"
            })
            
        st.table(pd.DataFrame(relatorio_fiscal))
        st.info("💡 **Dica de Conferência:** Compare o valor da coluna **'Imposto Apurado (Devido)'** com a soma da DAS / DARF de PIS, COFINS, IRPJ e CSLL efetivamente pagas no mês para identificar divergências.")
