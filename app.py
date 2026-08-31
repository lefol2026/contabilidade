import streamlit as st
import pandas as pd
import zipfile
import io
import gc

st.set_page_config(page_title="Consolidação Grupo - Livro Caixa", layout="wide")

st.markdown('<meta name="google" content="notranslate">', unsafe_allow_html=True)

st.title("📊 Painel Consolidado do Grupo — Módulo Livro Caixa & DRE")
st.caption("Modo Estável: Leitura de Relatórios Financeiros (CSV e Excel)")

# --- CONFIGURAÇÃO TRIBUTÁRIA ---
EMPRESAS_CONFIG = {
    "RTX IMPORTS COMERCIAL LTDA": {
        "cnpjs": ["55175101000195"],
        "icms_int": 0.06,
        "icms_ext": 0.013,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
    },
    "MCRTOTTI LTDA / BRA": {
        "cnpjs": ["25958668000177", "05221508000128", "25958668000339"],
        "icms_int": 0.06,
        "icms_ext": 0.013,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
    },
    "BR TOTTI LTDA / BW": {
        "cnpjs": ["23892392000146", "05221508000209"],
        "icms_int": 0.06,
        "icms_ext": 0.013,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
    },
    "BG ADESIVOS LTDA": {
        "cnpjs": ["05221462000124"],
        "icms_int": 0.0439,
        "icms_ext": 0.0439,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
    }
}

def extrair_dados_tabela(file_bytes, nome_arquivo):
    registros = []
    try:
        df = None
        if nome_arquivo.lower().endswith('.csv'):
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), sep=None, engine='python')
            except:
                df = pd.read_csv(io.BytesIO(file_bytes), sep=';')
        elif nome_arquivo.lower().endswith(('.xlsx', '.xls')):
            df = pd.read_excel(io.BytesIO(file_bytes))

        if df is not None and not df.empty:
            df.columns = [str(c).strip().upper() for c in df.columns]
            
            col_data = next((c for c in df.columns if any(k in c for k in ['DATA', 'DATE', 'EMISSAO'])), None)
            col_valor = next((c for c in df.columns if any(k in c for k in ['VALOR', 'VALOR TOTAL', 'VALOR (R$)', 'CREDITO', 'RECEITA'])), None)
            col_desc = next((c for c in df.columns if any(k in c for k in ['DESCRICAO', 'HISTORICO', 'EMPRESA', 'ORIGEM'])), None)

            if col_valor:
                for _, row in df.iterrows():
                    val = row[col_valor]
                    if pd.notna(val):
                        if isinstance(val, str):
                            val = val.replace("R$", "").replace(".", "").replace(",", ".").strip()
                        try:
                            val_float = float(val)
                        except:
                            continue

                        dt_str = str(row[col_data])[:10] if col_data and pd.notna(row[col_data]) else "2026-03-01"
                        desc_str = str(row[col_desc]) if col_desc and pd.notna(row[col_desc]) else nome_arquivo

                        registros.append({
                            'Arquivo': str(nome_arquivo),
                            'Data Emissao': dt_str,
                            'Descrição': desc_str,
                            'Tipo Operacao': "Venda (Saida)" if val_float >= 0 else "Compra (Entrada)",
                            'Valor Total (R$)': float(abs(val_float)),
                            'Empresa': "MCRTOTTI LTDA / BRA"
                        })
    except Exception:
        pass
    return registros

def processar_zip_caixa(zip_bytes):
    dados = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            for info in z.infolist():
                if info.filename.startswith('__MACOSX') or info.is_dir():
                    continue
                
                fname_lower = info.filename.lower()
                if fname_lower.endswith(('.csv', '.xlsx', '.xls')):
                    try:
                        content = z.read(info)
                        res = extrair_dados_tabela(content, info.filename.split('/')[-1])
                        if res:
                            dados.extend(res)
                        del content
                    except: pass
                elif fname_lower.endswith(('.zip', '.rar')):
                    try:
                        sub_bytes = z.read(info)
                        dados.extend(processar_zip_caixa(sub_bytes))
                        del sub_bytes
                    except: pass
    except Exception:
        pass
    return dados

# --- INTERFACE ---
st.sidebar.header("📁 Importar Livro Caixa/DRE")
arquivos_subidos = st.sidebar.file_uploader(
    "Suba relatórios em Excel, CSV ou pacotes .ZIP", 
    type=["zip", "csv", "xlsx", "xls"], 
    accept_multiple_files=True,
    key="file_up"
)

st.sidebar.markdown("---")
btn_processar = st.sidebar.button("➕ Processar Livro Caixa", type="primary", key="btn_proc")

if st.sidebar.button("🗑️ Limpar Historico Acumulado", key="btn_clear"):
    if 'df_caixa' in st.session_state:
        del st.session_state['df_caixa']
    st.sidebar.success("Historico apagado!")
    st.rerun()

# --- PROCESSAMENTO ---
if btn_processar and arquivos_subidos:
    novos_dados = []
    with st.spinner("⏳ Lendo relatórios e consolidando faturamento..."):
        for arq in arquivos_subidos:
            try:
                content = arq.read()
                if arq.name.lower().endswith('.zip'):
                    novos_dados.extend(processar_zip_caixa(content))
                elif arq.name.lower().endswith(('.csv', '.xlsx', '.xls')):
                    res = extrair_dados_tabela(content, arq.name)
                    if res:
                        novos_dados.extend(res)
                del content
            except Exception as e:
                st.error(f"Erro ao processar {arq.name}: {e}")
            gc.collect()

    if novos_dados:
        df_novos = pd.DataFrame(novos_dados)
        df_novos['Data_Parsed'] = pd.to_datetime(df_novos['Data Emissao'], errors='coerce')
        df_novos['Ano'] = df_novos['Data_Parsed'].dt.year.fillna(2026).astype(int)
        df_novos['Mes'] = df_novos['Data_Parsed'].dt.month.fillna(3).astype(int)

        if 'df_caixa' in st.session_state:
            df_existente = st.session_state['df_caixa']
            df_combinado = pd.concat([df_existente, df_novos], ignore_index=True)
            st.session_state['df_caixa'] = df_combinado
        else:
            st.session_state['df_caixa'] = df_novos

        st.success(f"✅ Processados {len(novos_dados)} lançamentos com sucesso!")
        gc.collect()
    else:
        st.warning("⚠️ Nenhum arquivo de Livro Caixa válido (CSV/Excel) foi extraído.")

# --- EXIBIÇÃO DE RESULTADOS ---
if 'df_caixa' in st.session_state and not st.session_state['df_caixa'].empty:
    df_caixa = st.session_state['df_caixa']
    
    st.info(f"📌 **Total Acumulado:** {len(df_caixa)} Lançamentos Financeiros.")

    anos_disp = sorted([int(a) for a in df_caixa['Ano'].unique()])
    
    st.sidebar.header("📅 Filtro de Periodo")
    ano_sel = st.sidebar.selectbox("Selecione o Ano", anos_disp, index=len(anos_disp)-1 if anos_disp else 0, key="sel_ano")
    
    meses_dict = {
        1: "Janeiro", 2: "Fevereiro", 3: "Marco", 4: "Abril",
        5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
        9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
    }
    mes_sel = st.sidebar.selectbox("Selecione o Mes", list(meses_dict.keys()), format_func=lambda x: meses_dict[x], key="sel_mes")

    df_mes = df_caixa[(df_caixa['Ano'] == ano_sel) & (df_caixa['Mes'] == mes_sel)]
    vendas_mes = df_mes[df_mes['Tipo Operacao'] == "Venda (Saida)"]['Valor Total (R$)'].sum() if not df_mes.empty else 0.0
    
    piscofins = vendas_mes * 0.0365
    irpjcsll = vendas_mes * 0.0228
    icms = vendas_mes * 0.06
    imposto_total = piscofins + irpjcsll + icms

    st.markdown(f"### 🔄 Resumo do Caixa — {meses_dict[mes_sel]}/{ano_sel}")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Faturamento Caixa", f"R$ {vendas_mes:,.2f}")
    c2.metric("ICMS Estimado (6%)", f"R$ {icms:,.2f}")
    c3.metric("PIS/COFINS (3.65%)", f"R$ {piscofins:,.2f}")
    c4.metric("IRPJ/CSLL (2.28%)", f"R$ {irpjcsll:,.2f}")
    c5.metric("Total Tributos", f"R$ {imposto_total:,.2f}")

    st.markdown("---")
    st.subheader("📋 Lançamentos do Período")
    if not df_mes.empty:
        st.dataframe(
            df_mes[['Arquivo', 'Data Emissao', 'Descrição', 'Tipo Operacao', 'Valor Total (R$)']], 
            use_container_width=True,
            key="df_display"
        )
    else:
        st.info("Nenhum lançamento encontrado para o mês e ano selecionados.")
