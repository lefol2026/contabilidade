import streamlit as st
import pandas as pd

# Configuração visual do Painel
st.set_page_config(page_title="Painel Fiscal & DP - Consultoria", layout="wide")

# Cabeçalho da Consultoria
st.title("📊 Gestão Fiscal & DP Assistida por IA")
st.markdown("### **Cliente:** Grupo E-commerce (1 Lucro Real + 3 Lucro Presumido)")

st.divider()

# Indicadores Principais (Cards)
col1, col2, col3, col4 = st.columns(4)
col1.metric("Faturamento Mês", "R$ 850.000", "+15%")
col2.metric("Impostos Apurados", "R$ 62.400", "-4%")
col3.metric("Créditos Monofásicos", "R$ 12.850", "Disponível")
col4.metric("Status eSocial / DP", "100% Ok", "Sólides Sync")

st.divider()

# Gráfico de Evolução Tributária
col_grafico, col_alertas = st.columns([2, 1])

with col_grafico:
    st.subheader("📈 Projeção Faturamento vs Impostos")
    dados = pd.DataFrame({
        'Mês': ['Mai', 'Jun', 'Jul', 'Ago'],
        'Faturamento': [720000, 780000, 810000, 850000],
        'Impostos': [55000, 58000, 60000, 62400]
    })
    st.line_chart(dados, x='Mês', y=['Faturamento', 'Impostos'])

with col_alertas:
    st.subheader("🚨 Diagnósticos da IA")
    st.warning("⚠️ **Mercado Livre Full:** Divergência de estoque no CFOP 5.905 identificada no Olist.")
    st.info("ℹ️ **Reforma Tributária:** 12 produtos NCM ajustados para transição IBS/CBS.")
    st.success("✅ **Sólides DP:** Folha e ponto auditados de acordo com a CCT do Sindicato.")

st.divider()
st.caption("Desenvolvido para Consultoria Contábil | Servidor Ativo via Railway")
