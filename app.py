import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import zipfile
import io
import gc

st.set_page_config(page_title="Consolidação Grupo - Painel Fiscal RET/TTS", layout="wide")

st.title("📊 Painel Consolidado do Grupo — Vendas, Compras & Apuração PIS/COFINS/RET")
st.caption("Versão Otimizada com Varredura Profunda de Pastas do Google Drive")

# --- CONFIGURAÇÃO TRIBUTÁRIA DAS EMPRESAS (RETs / e-PTA-RE) ---
EMPRESAS_CONFIG = {
    "RTX IMPORTS COMERCIAL LTDA": {
        "cnpjs": ["55175101000195"],
        "icms_int": 0.06,      # TTS MG Venda Interna (6.0%)[cite: 3, 5]
        "icms_ext": 0.013,     # TTS MG Venda Interestadual (1.3%)[cite: 3, 5]
        "pis": 0.0065,         # PIS Cumulativo (0.65%)
        "cofins": 0.0300,      # COFINS Cumulativo (3.00%)
        "irpj": 0.0120,        # IRPJ Presumido (1.20%)
        "csll": 0.0108,        # CSLL Presumido (1.08%)
        "regime": "TTS E-Commerce / Corredor Importação"[cite: 3, 5]
    },
    "MCRTOTTI LTDA / BRA": {
        "cnpjs": ["25958668000177", "05221508000128"],
        "icms_int": 0.06,      # TTS MG Venda Interna (6.0%)[cite: 1]
        "icms_ext": 0.013,     # TTS MG Venda Interestadual (1.3%)[cite: 1]
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
        "regime": "TTS E-Commerce / Lucro Presumido"[cite: 1]
    },
    "BR TOTTI LTDA / BW": {
        "cnpjs": ["23892392000146", "05221508000209"],
        "icms_int": 0.06,      # TTS MG Venda Interna (6.0%)[cite: 2]
        "icms_ext": 0.013,     # TTS MG Venda Interestadual (1.3%)[cite: 2]
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
        "regime": "TTS E-Commerce / Lucro Presumido"[cite: 2]
    },
    "BG ADESIVOS LTDA": {
        "cnpjs": ["05221462000124"],
        "icms_int": 0.0439,
        "icms_ext": 0.0439,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
        "regime": "Lucro Presumido Padrão"
    }
}

ALL_CNPJS_GRUPO = set(cnpj for emp in EMPRESAS_CONFIG.values() for cnpj in emp["cnpjs"])

# --- FUNÇÃO DE LEITURA E EXTRAÇÃO DE DADOS DE XML ---
def extrair_dados_xml(xml_bytes, nome_arquivo):
    try:
        # Tenta decodificar o conteúdo para string/stream limpo
        xml_str = xml_bytes.strip()
        if not xml_str.startswith(b'<'):
            # Ignora arquivos que não sejam estruturas XML
            return None
            
        root = ET.fromstring(xml_str)
        
        # Trata namespaces do portal fiscal
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        
        inf_nfe = root.find('.//nfe:infNFe', ns)
        if inf_nfe is None:
            inf_nfe = root.find('.//{http://www.portalfiscal.inf.br/nfe}infNFe')
        if inf_nfe is None:
            # Busca genérica sem namespace
            for elem in root.iter():
                if elem.tag.endswith('infNFe'):
                    inf_nfe = elem
                    break

        if inf_nfe is not None:
            dt_emissao = ""
            raz_emit, cnpj_emit = "Desconhecido", ""
            raz_dest, cnpj_dest, uf_dest = "Consumidor Final", "", "MG"
            v_nf = 0.0

            # Iteração nos elementos do XML
            for sub in inf_nfe:
                tag = sub.tag.split('}')[-1] if '}' in sub.tag else sub.tag
                
                if tag == 'ide':
                    for child in sub:
                        ctag = child.tag.split('}')[-1]
                        if ctag in ['dhEmi', 'dEmi'] and child.text:
                            dt_emissao = child.text[:10]
                            
                elif tag == 'emit':
                    for child in sub:
                        ctag = child.tag.split('}')[-1]
                        if ctag == 'xNome' and child.text: raz_emit = child.text
                        elif ctag == 'CNPJ' and child.text: cnpj_emit = child.text
                        
                elif tag == 'dest':
                    for child in sub:
                        ctag = child.tag.split('}')[-1]
                        if ctag == 'xNome' and child.text: raz_dest = child.text
                        elif ctag == 'CNPJ' and child.text: cnpj_dest = child.text
                        elif ctag == 'enderDest':
                            for ender_child in child:
                                etag = ender_child.tag.split('}')[-1]
                                if etag == 'UF' and ender_child.text: uf_dest = ender_child.text
                                
                elif tag == 'total':
                    for child in sub.iter():
                        ctag = child.tag.split('}')[-1]
                        if ctag == 'vNF' and child.text:
                            try: v_nf = float(child.text)
                            except: v_nf = 0.0

            cnpj_emit_limpo = cnpj_emit.replace(".", "").replace("/", "").replace("-", "").strip()
            cnpj_dest_limpo = cnpj_dest.replace(".", "").replace("/", "").replace("-", "").strip()
            
            tipo_operacao = "Venda (Saída)" if cnpj_emit_limpo in ALL_CNPJS_GRUPO else "Compra (Entrada)"
            
            return {
                'Arquivo': str(nome_arquivo),
                'Tipo Operação': tipo_operacao,
                'CNPJ Emitente': cnpj_emit_limpo,
                'Emitente': raz_emit,
                'CNPJ Destinatário': cnpj_dest_limpo,
                'Destinatário': raz_dest,
                'UF Destino': uf_dest.upper(),
                'Data Emissão': dt_emissao,
                'Valor Total (R$)': v_nf
            }
    except Exception:
        pass
    return None

def processar_zip_recursivo(zip_bytes):
    dados = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for info in z.infolist():
                if info.filename.startswith('__MACOSX') or info.is_dir():
                    continue
                
                fname_lower = info.filename.lower()
                
                # Processa arquivos com extensão XML ou arquivos sem extensão vindos do Drive
                if fname_lower.endswith('.xml') or (not '.' in fname_lower.split('/')[-1] and not fname_lower.endswith('/')):
                    try:
                        content = z.read(info)
                        res = extrair_dados_xml(content, info.filename.split('/')[-1])
                        if res: 
                            dados.append(res)
                        del content
                    except: pass
                # Processa sub-pacotes compactados
                elif fname_lower.endswith('.zip') or fname_lower.endswith('.rar'):
                    try:
                        sub_bytes = z.read(info)
                        dados.extend(processar_zip_recursivo(sub_bytes))
                        del sub_bytes
                    except: pass
    except Exception:
        pass
    return dados

# --- INTERFACE E BARRA LATERAL ---
st.sidebar.header("📁 Importar Arquivos")
arquivos_subidos = st.sidebar.file_uploader(
    "Suba seus arquivos .ZIP ou .XML", 
    type=["zip", "xml"], 
    accept_multiple_files=True,
    key="file_up"
)

st.sidebar.markdown("---")
btn_processar = st.sidebar.button("➕ Adicionar/Processar Notas", type="primary", key="btn_proc")

if st.sidebar.button("🗑️ Limpar Histórico Acumulado", key="btn_clear"):
    if 'df_nfs' in st.session_state:
        del st.session_state['df_nfs']
    st.sidebar.success("Histórico apagado!")
    st.rerun()

# --- PROCESSAMENTO PRINCIPAL ---
if btn_processar and arquivos_subidos:
    novos_dados = []
    with st.spinner("⏳ Efetuando varredura profunda de XMLs nos pacotes..."):
        for arq in arquivos_subidos:
            try:
                content = arq.read()
                if arq.name.lower().endswith('.zip'):
                    novos_dados.extend(processar_zip_recursivo(content))
                elif arq.name.lower().endswith('.xml'):
                    res = extrair_dados_xml(content, arq.name)
                    if res: novos_dados.append(res)
                del content
            except Exception as e:
                st.error(f"Erro ao ler {arq.name}: {e}")
            gc.collect()

    if novos_dados:
        df_novos = pd.DataFrame(novos_dados)
        df_novos['Data_Parsed'] = pd.to_datetime(df_novos['Data Emissão'], errors='coerce')
        df_novos['Ano'] = df_novos['Data_Parsed'].dt.year
        df_novos['Mês'] = df_novos['Data_Parsed'].dt.month
        
        df_novos['Tipo Operação'] = df_novos['Tipo Operação'].astype('category')
        df_novos['UF Destino'] = df_novos['UF Destino'].astype('category')

        if 'df_nfs' in st.session_state:
            df_existente = st.session_state['df_nfs']
            df_combinado = pd.concat([df_existente, df_novos], ignore_index=True).drop_duplicates(
                subset=['Arquivo', 'Valor Total (R$)', 'Data Emissão']
            )
            st.session_state['df_nfs'] = df_combinado
        else:
            st.session_state['df_nfs'] = df_novos

        st.success(f"✅ Processadas {len(novos_dados)} notas fiscais com sucesso!")
        gc.collect()
    else:
        st.warning("⚠️ Nenhum XML de NF-e válido foi extraído dos arquivos.")

# --- EXIBIÇÃO DO PAINEL DE DADOS ---
if 'df_nfs' in st.session_state and not st.session_state['df_nfs'].empty:
    df_nfs = st.session_state['df_nfs']
    
    st.info(f"📌 **Total Acumulado:** {len(df_nfs)} Notas Fiscais salvas na memória.")

    anos_disp = sorted([int(a) for a in df_nfs['Ano'].dropna().unique()])
    
    st.sidebar.header("📅 Filtro de Período")
    ano_sel = st.sidebar.selectbox("Selecione o Ano", anos_disp, index=len(anos_disp)-1 if anos_disp else 0, key="sel_ano")
    
    meses_dict = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    mes_sel = st.sidebar.selectbox("Selecione o Mês", list(meses_dict.keys()), format_func=lambda x: meses_dict[x], key="sel_mes")

    tab1, tab2, tab3 = st.tabs(["📅 Visão Mensal", "📊 Resumo Anual", "📑 Apuração Fiscal RET/TTS"])

    with tab1:
        df_mes = df_nfs[(df_nfs['Ano'] == ano_sel) & (df_nfs['Mês'] == mes_sel)]
        vendas_mes = df_mes[df_mes['Tipo Operação'] == "Venda (Saída)"]['Valor Total (R$)'].sum() if not df_mes.empty else 0.0
        compras_mes = df_mes[df_mes['Tipo Operação'] == "Compra (Entrada)"]['Valor Total (R$)'].sum() if not df_mes.empty else 0.0
        resultado_mes = vendas_mes - compras_mes
        
        imposto_total_mes = 0.0
        pis_total = 0.0
        cofins_total = 0.0
        
        if not df_mes.empty:
            for emp_nome, emp_info in EMPRESAS_CONFIG.items():
                vendas_int = df_mes[(df_mes['Tipo Operação'] == "Venda (Saída)") & (df_mes['CNPJ Emitente'].isin(emp_info['cnpjs'])) & (df_mes['UF Destino'] == 'MG')]['Valor Total (R$)'].sum()
                vendas_ext = df_mes[(df_mes['Tipo Operação'] == "Venda (Saída)") & (df_mes['CNPJ Emitente'].isin(emp_info['cnpjs'])) & (df_mes['UF Destino'] != 'MG')]['Valor Total (R$)'].sum()
                v_total_emp = vendas_int + vendas_ext
                
                icms = (vendas_int * emp_info['icms_int']) + (vendas_ext * emp_info['icms_ext'])
                pis = v_total_emp * emp_info['pis']
                cofins = v_total_emp * emp_info['cofins']
                irpj_csll = v_total_emp * (emp_info['irpj'] + emp_info['csll'])
                
                pis_total += pis
                cofins_total += cofins
                imposto_total_mes += (icms + pis + cofins + irpj_csll)

        st.subheader(f"🔄 Balanço Mensal — {meses_dict[mes_sel]}/{ano_sel}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Vendas Totais (Saídas)", f"R$ {vendas_mes:,.2f}")
        c2.metric("PIS Apurado (0.65%)", f"R$ {pis_total:,.2f}")
        c3.metric("COFINS Apurado (3.00%)", f"R$ {cofins_total:,.2f}")
        c4.metric("Imposto Total Devido", f"R$ {imposto_total_mes:,.2f}")

        st.markdown("---")
        st.subheader("📋 Detalhamento das Notas do Mês")
        if not df_mes.empty:
            st.dataframe(df_mes[['Arquivo', 'Tipo Operação', 'Data Emissão', 'Emitente', 'Destinatário', 'UF Destino', 'Valor Total (R$)']], use_container_width=True)
        else:
            st.info("Nenhuma nota fiscal encontrada para o mês e ano selecionados.")

    with tab2:
        st.subheader(f"📊 Consolidado Mês a Mês — Ano {ano_sel}")
        df_ano = df_nfs[df_nfs['Ano'] == ano_sel]
        
        resumo_anual = []
        for m_num, m_nome in meses_dict.items():
            df_m = df_ano[df_ano['Mês'] == m_num]
            v_vendas = df_m[df_m['Tipo Operação'] == "Venda (Saída)"]['Valor Total (R$)'].sum() if not df_m.empty else 0.0
            v_compras = df_m[df_m['Tipo Operação'] == "Compra (Entrada)"]['Valor Total (R$)'].sum() if not df_m.empty else 0.0
            
            resumo_anual.append({
                "Mês": m_nome,
                "Vendas (Saídas)": f"R$ {v_vendas:,.2f}",
                "Compras (Entradas)": f"R$ {v_compras:,.2f}",
                "Resultado Operacional": f"R$ {(v_vendas - v_compras):,.2f}"
            })
            
        st.table(pd.DataFrame(resumo_anual))

    with tab3:
        st.subheader(f"📑 Apuração Fiscal Detalhada por Empresa — {meses_dict[mes_sel]}/{ano_sel}")
        relatorio_fiscal = []
        df_mes = df_nfs[(df_nfs['Ano'] == ano_sel) & (df_nfs['Mês'] == mes_sel)]
        
        for emp_nome, emp_info in EMPRESAS_CONFIG.items():
            v_int = 0.0
            v_ext = 0.0
            if not df_mes.empty:
                v_int = df_mes[(df_mes['Tipo Operação'] == "Venda (Saída)") & (df_mes['CNPJ Emitente'].isin(emp_info['cnpjs'])) & (df_mes['UF Destino'] == 'MG')]['Valor Total (R$)'].sum()
                v_ext = df_mes[(df_mes['Tipo Operação'] == "Venda (Saída)") & (df_mes['CNPJ Emitente'].isin(emp_info['cnpjs'])) & (df_mes['UF Destino'] != 'MG')]['Valor Total (R$)'].sum()
            
            v_total = v_int + v_ext
            icms_devido = (v_int * emp_info['icms_int']) + (v_ext * emp_info['icms_ext'])
            
            pis_devido = v_total * emp_info['pis']
            cofins_devido = v_total * emp_info['cofins']
            irpj_devido = v_total * emp_info['irpj']
            csll_devido = v_total * emp_info['csll']
            
            total_devido = icms_devido + pis_devido + cofins_devido + irpj_devido + csll_devido
            
            relatorio_fiscal.append({
                "Empresa": emp_nome,
                "Faturamento": f"R$ {v_total:,.2f}",
                "ICMS TTS (MG)": f"R$ {icms_devido:,.2f}",
                "PIS (0.65%)": f"R$ {pis_devido:,.2f}",
                "COFINS (3.00%)": f"R$ {cofins_devido:,.2f}",
                "IRPJ (1.20%)": f"R$ {irpj_devido:,.2f}",
                "CSLL (1.08%)": f"R$ {csll_devido:,.2f}",
                "Total Impostos": f"R$ {total_devido:,.2f}"
            })
            
        st.table(pd.DataFrame(relatorio_fiscal))
else:
    st.info("👈 Suba os arquivos e clique no botão **➕ Adicionar/Processar Notas**.")
