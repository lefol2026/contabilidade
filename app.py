import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import zipfile
import io
import gc

# Configuração da página - Deve ser a primeira linha executada
st.set_page_config(page_title="Consolidação Grupo - Painel Fiscal RET/TTS", layout="wide")

st.title("📊 Painel Consolidado do Grupo — Vendas, Compras & Apuração PIS/COFINS/RET")
st.caption("Versão Otimizada com Proteção de Memória e Estabilidade Tributária")

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

# --- FUNÇÃO DE LEITURA OTIMIZADA DE XML ---
def extrair_dados_xml(xml_content, nome_arquivo):
    try:
        context = ET.iterparse(io.BytesIO(xml_content), events=('end',))
        _, root = next(context)
        
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        
        inf_nfe = root.find('.//nfe:infNFe', ns)
        if inf_nfe is None:
            # Fallback para XMLs sem namespace prefixado
            inf_nfe = root.find('.//{http://www.portalfiscal.inf.br/nfe}infNFe')
            
        if inf_nfe is not None:
            ide = inf_nfe.find('nfe:ide', ns) if inf_nfe.find('nfe:ide', ns) is not None else inf_nfe.find('{http://www.portalfiscal.inf.br/nfe}ide')
            emit = inf_nfe.find('nfe:emit', ns) if inf_nfe.find('nfe:emit', ns) is not None else inf_nfe.find('{http://www.portalfiscal.inf.br/nfe}emit')
            dest = inf_nfe.find('nfe:dest', ns) if inf_nfe.find('nfe:dest', ns) is not None else inf_nfe.find('{http://www.portalfiscal.inf.br/nfe}dest')
            total = inf_nfe.find('.//nfe:ICMSTot', ns) if inf_nfe.find('.//nfe:ICMSTot', ns) is not None else inf_nfe.find('.//{http://www.portalfiscal.inf.br/nfe}ICMSTot')
            
            dt_emissao = ""
            if ide is not None:
                elem_dhemi = ide.find('nfe:dhEmi', ns) if ide.find('nfe:dhEmi', ns) is not None else ide.find('{http://www.portalfiscal.inf.br/nfe}dhEmi')
                if elem_dhemi is not None and elem_dhemi.text:
                    dt_emissao = elem_dhemi.text[:10]

            raz_emit, cnpj_emit = "Desconhecido", ""
            if emit is not None:
                e_nome = emit.find('nfe:xNome', ns) if emit.find('nfe:xNome', ns) is not None else emit.find('{http://www.portalfiscal.inf.br/nfe}xNome')
                e_cnpj = emit.find('nfe:CNPJ', ns) if emit.find('nfe:CNPJ', ns) is not None else emit.find('{http://www.portalfiscal.inf.br/nfe}CNPJ')
                if e_nome is not None and e_nome.text: raz_emit = e_nome.text
                if e_cnpj is not None and e_cnpj.text: cnpj_emit = e_cnpj.text

            raz_dest, cnpj_dest, uf_dest = "Consumidor Final", "", "MG"
            if dest is not None:
                d_nome = dest.find('nfe:xNome', ns) if dest.find('nfe:xNome', ns) is not None else dest.find('{http://www.portalfiscal.inf.br/nfe}xNome')
                d_cnpj = dest.find('nfe:CNPJ', ns) if dest.find('nfe:CNPJ', ns) is not None else dest.find('{http://www.portalfiscal.inf.br/nfe}CNPJ')
                ender = dest.find('nfe:enderDest', ns) if dest.find('nfe:enderDest', ns) is not None else dest.find('{http://www.portalfiscal.inf.br/nfe}enderDest')
                
                if d_nome is not None and d_nome.text: raz_dest = d_nome.text
                if d_cnpj is not None and d_cnpj.text: cnpj_dest = d_cnpj.text
                if ender is not None:
                    d_uf = ender.find('nfe:UF', ns) if ender.find('nfe:UF', ns) is not None else ender.find('{http://www.portalfiscal.inf.br/nfe}UF')
                    if d_uf is not None and d_uf.text: uf_dest = d_uf.text

            v_nf = 0.0
            if total is not None:
                e_vnf = total.find('nfe:vNF', ns) if total.find('nfe:vNF', ns) is not None else total.find('{http://www.portalfiscal.inf.br/nfe}vNF')
                if e_vnf is not None and e_vnf.text:
                    try: v_nf = float(e_vnf.text)
                    except: v_nf = 0.0

            cnpj_emit_limpo = cnpj_emit.replace(".", "").replace("/", "").replace("-", "").strip()
            cnpj_dest_limpo = cnpj_dest.replace(".", "").replace("/", "").replace("-", "").strip()
            
            tipo_operacao = "Venda (Saída)" if cnpj_emit_limpo in ALL_CNPJS_GRUPO else "Compra (Entrada)"
            
            res = {
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
            root.clear()
            return res
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
                if fname_lower.endswith('.xml'):
                    try:
                        content = z.read(info)
                        res = extrair_dados_xml(content, info.filename.split('/')[-1])
                        if res: dados.append(res)
                        del content
                    except: pass
                elif fname_lower.endswith('.zip'):
                    try:
                        sub_bytes = z.read(info)
                        dados.extend(processar_zip_recursivo(sub_bytes))
                        del sub_bytes
                    except: pass
    except: pass
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
    with st.spinner("⏳ Lendo e extraindo notas fiscais com otimização de memória..."):
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
        
        # Otimização dos tipos de dados para reduzir uso da memória RAM
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

        st.success(f"✅ Processadas {len(novos_dados)} notas com sucesso!")
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
    st.info("👈 Suba os arquivos fracionados (ex: por mês) e clique em **➕ Adicionar/Processar Notas**.")
