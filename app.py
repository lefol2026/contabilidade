import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import zipfile
import io
import gc

st.set_page_config(page_title="Consolidação Grupo - Painel Fiscal RET/TTS", layout="wide")

st.title("📊 Painel Consolidado do Grupo — Vendas, Compras & Apuração RET/TTS")
st.caption("Cálculo de Impostos Automatizado com Regras dos Regimes Especiais de Tributação (MG)")

# --- CONFIGURAÇÃO TRIBUTÁRIA DAS EMPRESAS (RETs / e-PTA-RE) ---
EMPRESAS_CONFIG = {
    "RTX IMPORTS COMERCIAL LTDA": {
        "cnpjs": ["55175101000195"],
        "icms_int": 0.06,      # TTS MG Venda Interna (6.0%)
        "icms_ext": 0.013,     # TTS MG Venda Interestadual (1.3%)
        "federais": 0.0693,    # PIS/COFINS/IRPJ/CSLL Lucro Presumido (6.93%)
        "regime": "TTS E-Commerce / Corredor Importação"
    },
    "MCRTOTTI LTDA / BRA": {
        "cnpjs": ["25958668000177", "05221508000128"],
        "icms_int": 0.06,      # TTS MG Venda Interna (6.0%)
        "icms_ext": 0.013,     # TTS MG Venda Interestadual (1.3%)
        "federais": 0.0693,    # Lucro Presumido (6.93%)
        "regime": "TTS E-Commerce / Lucro Presumido"
    },
    "BR TOTTI LTDA / BW": {
        "cnpjs": ["23892392000146", "05221508000209"],
        "icms_int": 0.06,      # TTS MG Venda Interna (6.0%)
        "icms_ext": 0.013,     # TTS MG Venda Interestadual (1.3%)
        "federais": 0.0693,    # Lucro Presumido (6.93%)
        "regime": "TTS E-Commerce / Lucro Presumido"
    },
    "BG ADESIVOS LTDA": {
        "cnpjs": ["05221462000124"],
        "icms_int": 0.0439,    # Padrão
        "icms_ext": 0.0439,    # Padrão
        "federais": 0.0693,    # Lucro Presumido
        "regime": "Lucro Presumido Padrão"
    }
}

# Todos os CNPJs do grupo unificados
ALL_CNPJS_GRUPO = [cnpj for emp in EMPRESAS_CONFIG.values() for cnpj in emp["cnpjs"]]

# --- BARRA LATERAL ---
st.sidebar.header("📁 Importar Arquivos")
arquivos_subidos = st.sidebar.file_uploader(
    "Suba um ou mais arquivos .ZIP", 
    type=["zip", "xml"], 
    accept_multiple_files=True
)

st.sidebar.markdown("---")
btn_processar = st.sidebar.button("➕ Adicionar/Processar Notas", type="primary")

if st.sidebar.button("🗑️ Limpar Todos os Dados Acumulados"):
    if 'df_nfs' in st.session_state:
        del st.session_state['df_nfs']
    st.sidebar.success("Histórico apagado! Você pode reiniciar a carga.")
    st.rerun()

def extrair_dados_xml(xml_stream, nome_arquivo):
    try:
        tree = ET.parse(xml_stream)
        root = tree.getroot()
        ns = {'nfe': 'http://www.portalfiscal.inf.br/nfe'}
        
        inf_nfe = root.find('.//nfe:infNFe', ns)
        if inf_nfe is not None:
            ide = inf_nfe.find('nfe:ide', ns)
            emit = inf_nfe.find('nfe:emit', ns)
            dest = inf_nfe.find('nfe:dest', ns)
            ender_dest = dest.find('nfe:enderDest', ns) if dest is not None else None
            total = inf_nfe.find('.//nfe:ICMSTot', ns)
            
            dt_emissao = ide.find('nfe:dhEmi', ns).text[:10] if (ide is not None and ide.find('nfe:dhEmi', ns) is not None) else ""
            raz_emit = emit.find('nfe:xNome', ns).text if (emit is not None and emit.find('nfe:xNome', ns) is not None) else "Desconhecido"
            cnpj_emit = emit.find('nfe:CNPJ', ns).text if (emit is not None and emit.find('nfe:CNPJ', ns) is not None) else ""
            
            raz_dest = dest.find('nfe:xNome', ns).text if (dest is not None and dest.find('nfe:xNome', ns) is not None) else "Consumidor Final"
            cnpj_dest = dest.find('nfe:CNPJ', ns).text if (dest is not None and dest.find('nfe:CNPJ', ns) is not None) else ""
            uf_dest = ender_dest.find('nfe:UF', ns).text if (ender_dest is not None and ender_dest.find('nfe:UF', ns) is not None) else "MG"
            
            v_nf = float(total.find('nfe:vNF', ns).text) if (total is not None and total.find('nfe:vNF', ns) is not None) else 0.0
            
            cnpj_emit_limpo = cnpj_emit.replace(".", "").replace("/", "").replace("-", "").strip()
            cnpj_dest_limpo = cnpj_dest.replace(".", "").replace("/", "").replace("-", "").strip()
            
            tipo_operacao = "Venda (Saída)" if cnpj_emit_limpo in ALL_CNPJS_GRUPO else "Compra (Entrada)"
            
            return {
                'Arquivo': nome_arquivo,
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

def processar_zip_obj(z_obj):
    dados = []
    for info in z_obj.infolist():
        if info.filename.startswith('__MACOSX') or info.is_dir():
            continue
            
        fname_lower = info.filename.lower()
        if fname_lower.endswith('.xml'):
            try:
                with z_obj.open(info) as xml_file:
                    res = extrair_dados_xml(xml_file, info.filename.split('/')[-1])
                    if res:
                        dados.append(res)
            except Exception:
                pass
        elif fname_lower.endswith('.zip'):
            try:
                sub_bytes = z_obj.read(info)
                with zipfile.ZipFile(io.BytesIO(sub_bytes)) as sub_z:
                    dados.extend(processar_zip_obj(sub_z))
                del sub_bytes
                gc.collect()
            except Exception:
                pass
    return dados

# --- PROCESSAMENTO ACUMULATIVO ---
if btn_processar and arquivos_subidos:
    status_container = st.empty()
    status_container.info("⏳ Processando arquivos com apuração tributária de MG...")
    
    novos_dados = []
    for arq in arquivos_subidos:
        if arq.name.lower().endswith('.zip'):
            try:
                with zipfile.ZipFile(arq) as z:
                    novos_dados.extend(processar_zip_obj(z))
            except Exception as e:
                st.error(f"Erro ao ler {arq.name}: {e}")
        elif arq.name.lower().endswith('.xml'):
            res = extrair_dados_xml(arq, arq.name)
            if res:
                novos_dados.append(res)
        gc.collect()

    status_container.empty()

    if novos_dados:
        df_novos = pd.DataFrame(novos_dados)
        df_novos['Data_Parsed'] = pd.to_datetime(df_novos['Data Emissão'], errors='coerce')
        df_novos['Ano'] = df_novos['Data_Parsed'].dt.year
        df_novos['Mês'] = df_novos['Data_Parsed'].dt.month
        
        if 'df_nfs' in st.session_state:
            df_existente = st.session_state['df_nfs']
            df_combinado = pd.concat([df_existente, df_novos]).drop_duplicates(subset=['Arquivo', 'Valor Total (R$)', 'Data Emissão'])
            st.session_state['df_nfs'] = df_combinado
        else:
            st.session_state['df_nfs'] = df_novos

        st.success(f"✅ Adicionadas {len(novos_dados)} notas fiscais ao acumulado!")
    else:
        st.warning("⚠️ Nenhum XML de NF-e válido foi encontrado.")

# --- PAINEL PRINCIPAL ---
if 'df_nfs' in st.session_state and not st.session_state['df_nfs'].empty:
    df_nfs = st.session_state['df_nfs']
    
    st.info(f"📌 **Total Acumulado na Memória:** {len(df_nfs)} Notas Fiscais processadas.")

    anos_disp = sorted([int(a) for a in df_nfs['Ano'].dropna().unique()])
    
    st.sidebar.header("📅 Filtro de Período")
    ano_sel = st.sidebar.selectbox("Selecione o Ano", anos_disp, index=len(anos_disp)-1 if anos_disp else 0)
    
    meses_dict = {
        1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    mes_sel = st.sidebar.selectbox("Selecione o Mês", list(meses_dict.keys()), format_func=lambda x: meses_dict[x])

    tab1, tab2, tab3 = st.tabs(["📅 Visão Mensal", "📊 Resumo Anual", "📑 Apuração Fiscal RET/TTS"])

    with tab1:
        df_mes = df_nfs[(df_nfs['Ano'] == ano_sel) & (df_nfs['Mês'] == mes_sel)]
        vendas_mes = df_mes[df_mes['Tipo Operação'] == "Venda (Saída)"]['Valor Total (R$)'].sum() if not df_mes.empty else 0.0
        compras_mes = df_mes[df_mes['Tipo Operação'] == "Compra (Entrada)"]['Valor Total (R$)'].sum() if not df_mes.empty else 0.0
        resultado_mes = vendas_mes - compras_mes
        
        # Apuração Fiscal Mês
        imposto_total_mes = 0.0
        if not df_mes.empty:
            for emp_nome, emp_info in EMPRESAS_CONFIG.items():
                vendas_int = df_mes[(df_mes['Tipo Operação'] == "Venda (Saída)") & (df_mes['CNPJ Emitente'].isin(emp_info['cnpjs'])) & (df_mes['UF Destino'] == 'MG')]['Valor Total (R$)'].sum()
                vendas_ext = df_mes[(df_mes['Tipo Operação'] == "Venda (Saída)") & (df_mes['CNPJ Emitente'].isin(emp_info['cnpjs'])) & (df_mes['UF Destino'] != 'MG')]['Valor Total (R$)'].sum()
                
                icms = (vendas_int * emp_info['icms_int']) + (vendas_ext * emp_info['icms_ext'])
                federais = (vendas_int + vendas_ext) * emp_info['federais']
                imposto_total_mes += (icms + federais)

        st.subheader(f"🔄 Balanço Mensal — {meses_dict[mes_sel]}/{ano_sel}")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Vendas Totais (Saídas)", f"R$ {vendas_mes:,.2f}")
        c2.metric("Compras Totais (Entradas)", f"R$ {compras_mes:,.2f}")
        c3.metric("Resultado Bruto", f"R$ {resultado_mes:,.2f}")
        c4.metric("Imposto Total Apurado (RET+Fed)", f"R$ {imposto_total_mes:,.2f}")

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
        st.subheader(f"📑 Apuração Detalhada por RET / e-PTA-RE — {meses_dict[mes_sel]}/{ano_sel}")
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
            federais_devido = v_total * emp_info['federais']
            total_devido = icms_devido + federais_devido
            
            relatorio_fiscal.append({
                "Empresa": emp_nome,
                "Regime": emp_info['regime'],
                "Vendas Internas (MG)": f"R$ {v_int:,.2f}",
                "Vendas Interestaduais": f"R$ {v_ext:,.2f}",
                "Faturamento Total": f"R$ {v_total:,.2f}",
                "ICMS Efetivo (TTS)": f"R$ {icms_devido:,.2f}",
                "Imp. Federais (6.93%)": f"R$ {federais_devido:,.2f}",
                "Imposto Total Apurado": f"R$ {total_devido:,.2f}"
            })
            
        st.table(pd.DataFrame(relatorio_fiscal))
        st.info("💡 **Conferência Fiscal:** Compare o valor da coluna **'ICMS Efetivo (TTS)'** com a DAPI (campo 104.1 / código de receita 218-8) e os **'Imp. Federais'** com as DARFs de PIS, COFINS, IRPJ e CSLL.")
else:
    st.info("👈 Faça o upload dos arquivos `.zip` ou `.xml` e clique em **➕ Adicionar/Processar Notas**.")
