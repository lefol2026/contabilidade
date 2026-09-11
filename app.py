import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# Configuração da página
st.set_page_config(
    page_title="Executive B.I. — Apuração Fiscal",
    page_icon="👑",
    layout="wide",
)

st.title("👑 Executive B.I. — Apuração Fiscal & Conciliação")


# 1. Carregamento dos dados via CSV
@st.cache_data
def carregar_dados():
  try:
    df = pd.read_csv("dados_consolidados.csv")
    return df
  except Exception as e:
    st.error(f"Erro ao carregar o arquivo 'dados_consolidados.csv': {e}")
    return pd.DataFrame()


df = carregar_dados()

if df.empty:
  st.warning(
      "Nenhum documento fiscal foi carregado. Verifique se o arquivo"
      " 'dados_consolidados.csv' está no repositório do GitHub."
  )
else:
  st.success(f"Base consolidada com sucesso! Total de {len(df)} registros.")

  # 2. Filtros Laterais e Superiores
  col1, col2 = st.columns(2)

  with col1:
    empresas = ["TODAS AS EMPRESAS (GRUPO)"] + list(df["Empresa"].unique())
    empresa_sel = st.selectbox("🏢 Empresa:", empresas)

  with col2:
    meses = ["Consolidado Anual"] + sorted(list(df["Mês"].unique()))
    mes_sel = st.selectbox("📅 Mês:", meses)

  # Aplicação dos filtros
  df_filtrado = df.copy()

  if empresa_sel != "TODAS AS EMPRESAS (GRUPO)":
    df_filtrado = df_filtrado[df_filtrado["Empresa"] == empresa_sel]

  if mes_sel != "Consolidado Anual":
    df_filtrado = df_filtrado[df_filtrado["Mês"] == mes_sel]

  # 3. Cálculo dos Indicadores Fiscais
  faturamento = df_filtrado[
      df_filtrado["Tipo Operacao"].str.contains("Venda", case=False, na=False)
  ]["Valor"].sum()

  compras = df_filtrado[
      df_filtrado["Tipo Operacao"].str.contains("Compra", case=False, na=False)
  ]["Valor"].sum()

  # Estimativa de Alíquotas Impostos Fiscais (Simples/Lucro Presumido)
  icms_tts = faturamento * 0.06
  pis_cofins = faturamento * 0.0365
  irpj_csll = faturamento * 0.0228
  total_impostos = icms_tts + pis_cofins + irpj_csll

  # 4. Exibição das Métricas
  m1, m2, m3, m4, m5, m6 = st.columns(6)

  m1.metric("💰 FATURAMENTO", f"R$ {faturamento:,.2f}")
  m2.metric("🛒 COMPRAS", f"R$ {compras:,.2f}")
  m3.metric("🏛️ ICMS TTS", f"R$ {icms_tts:,.2f}")
  m4.metric("📊 PIS / COFINS", f"R$ {pis_cofins:,.2f}")
  m5.metric("⚖️ IRPJ / CSLL", f"R$ {irpj_csll:,.2f}")
  m6.metric("🚨 TOTAL IMPOSTOS", f"R$ {total_impostos:,.2f}")

  st.divider()

  # 5. Gráficos de Visualização
  g1, g2 = st.columns(2)

  with g1:
    st.subheader("📈 Faturamento por Mês")
    df_mes = (
        df_filtrado[
            df_filtrado["Tipo Operacao"].str.contains(
                "Venda", case=False, na=False
            )
        ]
        .groupby("Mês")["Valor"]
        .sum()
        .reset_index()
    )
    fig_mes = px.bar(
        df_mes,
        x="Mês",
        y="Valor",
        text_auto=".2s",
        color_discrete_sequence=["#1f77b4"],
    )
    st.plotly_chart(fig_mes, use_container_width=True)

  with g2:
    st.subheader("🏢 Faturamento por Empresa")
    df_emp = (
        df_filtrado[
            df_filtrado["Tipo Operacao"].str.contains(
                "Venda", case=False, na=False
            )
        ]
        .groupby("Empresa")["Valor"]
        .sum()
        .reset_index()
    )
    fig_emp = px.pie(
        df_emp, values="Valor", names="Empresa", hole=0.4, title="Participação"
    )
    st.plotly_chart(fig_emp, use_container_width=True)

  # 6. Tabela Detalhada
  st.subheader("📋 Tabela de Documentos Fiscais Auditados")
  st.dataframe(
      df_filtrado[["Arquivo", "Mês", "Empresa", "Tipo Operacao", "Valor"]],
      use_container_width=True,
  )
