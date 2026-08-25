import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import zipfile
import io
import gc

st.set_page_config(page_title="Consolidação Grupo - Painel Fiscal", layout="wide")

# Desativa a tradução no HTML
st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

st.title("📊 Painel Consolidado do Grupo — Vendas, Compras & Apuração PIS/COFINS/RET")

EMPRESAS_CONFIG = {
    "RTX IMPORTS COMERCIAL LTDA": {
        "cnpjs": ["55175101000195"],
        "icms_int": 0.06,
        "icms_ext": 0.013,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
        "regime": "TTS E-Commerce / Corredor Importacao"
    },
    "MCRTOTTI LTDA / BRA": {
        "cnpjs": ["25958668000177", "05221508000128"],
        "icms_int": 0.06,
        "icms_ext": 0.013,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
        "regime": "TTS E-Commerce / Lucro Presumido"
    },
    "BR TOTTI LTDA / BW": {
        "cnpjs": ["23892392000146", "05221508000209"],
        "icms_int": 0.06,
        "icms_ext": 0.013,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
        "regime": "TTS E-Commerce / Lucro Presumido"
    },
    "BG ADESIVOS LTDA": {
        "cnpjs": ["05221462000124"],
        "icms_int": 0.0439,
        "icms_ext": 0.0439,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
        "regime": "Lucro Presumido Padrao"
    }
}

ALL_CNPJS_GRUPO = set(cnpj for emp in EMPRESAS_CONFIG.values() for cnpj in emp["cnpjs"])

def extrair_dados_xml(xml_bytes, nome_arquivo):
    try:
        xml_str = xml_bytes.strip()
        if not xml_str.startswith(b'<'):
            return None
            
        root = ET.fromstring(xml_str)
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        
        inf_nfe = root.find('.//nfe:infNFe', ns)
        if inf_nfe is None:
            inf_nfe = root.find('.//{http://www.portalfiscal.inf.br/nfe}infNFe')
        if inf_nfe is None:
            for elem in root.iter():
                if elem.tag.endswith('infNFe'):
                    inf_nfe = elem
                    break

        if inf_nfe is not None:
            dt_emissao = ""
            raz_emit, cnpj_emit = "Desconhecido", ""
            raz_dest, cnpj_dest, uf_dest = "Consumidor Final", "", "MG"
            v_nf = 0.0
            cfop_nota = "N/A"

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
                                
                elif tag == 'det':
                    prod = sub.find('.//nfe:prod', ns) if sub.find('.//nfe:prod', ns) is not None else sub.find('.//prod')
                    if prod is not None:
                        elem_cfop = prod.find('nfe:cfop', ns) if prod.find('nfe:cfop', ns) is not None else prod.find('cfop')
                        if elem_cfop is not None and elem_cfop.text:
                            cfop_nota = elem_cfop.text.strip()

                elif tag == 'total':
                    for child in sub.iter():
                        ctag = child.tag.split('}')[-1]
                        if ctag == 'vNF' and child.text:
                            try: v_nf = float(child.text)
                            except: v_nf = 0.0

            cnpj_emit_limpo = cnpj_emit.replace(".", "").replace("/", "").replace("-", "").strip()
            cnpj_dest_limpo = cnpj_dest.replace(".", "").replace("/", "").replace("-", "").strip()
            
            tipo_operacao = "Venda (Saida)" if cnpj_emit_limpo in ALL_CNPJS_GRUPO else "Compra (Entrada)"
            
            return {
                'Arquivo': str(nome_arquivo),
                'Tipo Operacao': tipo_operacao,
                'CNPJ Emitente': cnpj_emit_limpo,
                'Emitente': raz_emit,
                'CNPJ Destinatario': cnpj_dest_limpo,
                'Destinatario': raz_dest,
                'UF Destino': uf_dest.upper(),
                'Data Emissao': dt_emissao,
                'Valor Total (R$)': v_nf,
                'CFOP': cfop_nota
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
                if fname_lower.endswith('.xml') or (not '.' in fname_lower.split('/')[-1] and not fname_lower.endswith('/')):
                    try:
                        content = z.read(info)
                        res = extrair_dados_xml(content, info.filename.split('/')[-1])
                        if res: dados.append(res)
                        del content
                    except: pass
                elif fname_lower.endswith('.zip') or fname_lower.endswith('.rar'):
                    try:
                        sub_bytes = z.read(info)
                        dados.extend(processar_zip_recursivo(sub_bytes))
                        del sub_bytes
                    except: pass
    except Exception:
        pass
    return dados

# --- SIDEBAR ---
st.sidebar.header("📁 Importar Arquivos")
arquivos_subidos = st.sidebar.file_uploader(
    "Suba seus arquivos .ZIP ou .XML", 
    type=["zip", "xml"], 
    accept_multiple_files=True,
    key="file_up"
)

st.sidebar.markdown("---")
btn_processar = st.sidebar.button("➕ Adicionar/Processar Notas", type="primary", key="btn_proc")

if st.sidebar.button("🗑️ Limpar Historico Acumulado", key="btn_clear"):
    if 'df_nfs' in st.session_state:
        del st.session_state['df_nfs']
    st.sidebar.success("Historico apagado!")
    st.rerun()

# --- PROCESSAMENTO ---
if btn_processar and arquivos_subidos:
    novos_dados = []
    with st.spinner("⏳ Lendo arquivos..."):
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
        df_novos['Data_Parsed'] = pd.to_datetime(df_novos['Data Emissao'], errors='coerce')
        df_novos['Ano'] = df_novos['Data_Parsed'].dt.year
        df_novos['Mes'] = df_novos['Data_Parsed'].dt.month

        if 'df_nfs' in st.session_state:
            df_existente = st.session_state['df_nfs']
            df_combinado = pd.concat([df_existente, df_novos], ignore_index=True).drop_duplicates(
                subset=['Arquivo', 'Valor Total (R$)', 'Data Emissao']
            )
            st.session_state['df_nfs'] = df_combinado
        else:
            st.session_state['df_nfs'] = df_novos

        st.success(f"✅ Processadas {len(novos_dados)} notas com sucesso!")
        gc.collect()

# --- EXIBIÇÃO ---
if 'df_nfs' in st.session_state and not st.session_state['df_nfs'].empty:
    df_nfs = st.session_state['df_nfs']
    
    colunas_obrigatorias = ['Arquivo', 'Tipo Operacao', 'CFOP', 'Data Emissao', 'Emitente', 'Destinatario', 'UF Destino', 'Valor Total (R$)']
    for col in colunas_obrigatorias:
        if col not in df_nfs.columns:
            df_nfs[col] = "N/A"
    
    st.info(f"📌 **Total Acumulado:** {len(df_nfs)} Notas Fiscais salvas na memoria.")

    anos_disp = sorted([int(a) for a in df_nfs['Ano'].dropna().unique()])
    
    st.sidebar.header("📅 Filtro de Periodo")
    ano_sel = st.sidebar.selectbox("Selecione o Ano", anos_disp, index=len(anos_disp)-1 if anos_disp else 0, key="sel_ano")
    
    meses_dict = {
        1: "Janeiro", 2: "Fevereiro", 3: "Marco", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    mes_sel = st.sidebar.selectbox("Selecione o Mes", list(meses_dict.keys()), format_func=lambda x: meses_dict[x], key="sel_mes")

    # Renderização via HTML estático sem componentes reativos quebráveis
    df_mes = df_nfs[(df_nfs['Ano'] == ano_sel) & (df_nfs['Mes'] == mes_sel)]
    vendas_mes = df_mes[df_mes['Tipo Operacao'] == "Venda (Saida)"]['Valor Total (R$)'].sum() if not df_mes.empty else 0.0
    
    imposto_total_mes = 0.0
    piscofins_total = 0.0
    irpjcsll_total = 0.0
    icms_total = 0.0
    
    if not df_mes.empty:
        for emp_nome, emp_info in EMPRESAS_CONFIG.items():
            vendas_int = df_mes[(df_mes['Tipo Operacao'] == "Venda (Saida)") & (df_mes['CNPJ Emitente'].isin(emp_info['cnpjs'])) & (df_mes['UF Destino'] == 'MG')]['Valor Total (R$)'].sum()
            vendas_ext = df_mes[(df_mes['Tipo Operacao'] == "Venda (Saida)") & (df_mes['CNPJ Emitente'].isin(emp_info['cnpjs'])) & (df_mes['UF Destino'] != 'MG')]['Valor Total (R$)'].sum()
            v_total_emp = vendas_int + vendas_ext
            
            icms = (vendas_int * emp_info['icms_int']) + (vendas_ext * emp_info['icms_ext'])
            pis = v_total_emp * emp_info['pis']
            cofins = v_total_emp * emp_info['cofins']
            irpj = v_total_emp * emp_info['irpj']
            csll = v_total_emp * emp_info['csll']
            
            icms_total += icms
            piscofins_total += (pis + cofins)
            irpjcsll_total += (irpj + csll)
            imposto_total_mes += (icms + pis + cofins + irpj + csll)

    st.markdown(f"### 🔄 Balanco Mensal — {meses_dict[mes_sel]}/{ano_sel}")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Vendas Totais", f"R$ {vendas_mes:,.2f}")
    c2.metric("ICMS TTS (MG)", f"R$ {icms_total:,.2f}")
    c3.metric("PIS/COFINS (3.65%)", f"R$ {piscofins_total:,.2f}")
    c4.metric("IRPJ/CSLL (2.28%)", f"R$ {irpjcsll_total:,.2f}")
    c5.metric("Total Devido", f"R$ {imposto_total_mes:,.2f}")

    st.markdown("---")
    st.subheader("📑 Apuracao Fiscal Detalhada por Empresa")
    
    relatorio_fiscal = []
    for emp_nome, emp_info in EMPRESAS_CONFIG.items():
        v_int = 0.0
        v_ext = 0.0
        if not df_mes.empty:
            v_int = df_mes[(df_mes['Tipo Operacao'] == "Venda (Saida)") & (df_mes['CNPJ Emitente'].isin(emp_info['cnpjs'])) & (df_mes['UF Destino'] == 'MG')]['Valor Total (R$)'].sum()
            v_ext = df_mes[(df_mes['Tipo Operacao'] == "Venda (Saida)") & (df_mes['CNPJ Emitente'].isin(emp_info['cnpjs'])) & (df_mes['UF Destino'] != 'MG')]['Valor Total (R$)'].sum()
        
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
            "PIS/COFINS (3.65%)": f"R$ {(pis_devido + cofins_devido):,.2f}",
            "IRPJ/CSLL (2.28%)": f"R$ {(irpj_devido + csll_devido):,.2f}",
            "Total Impostos": f"R$ {total_devido:,.2f}"
        })
        
    st.write(pd.DataFrame(relatorio_fiscal).to_html(index=False), unsafe_allow_html=True)
