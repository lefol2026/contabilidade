import streamlit as st
import pandas as pd

# Configuração da página
st.set_page_config(page_title="Consolidação Grupo E-commerce & Inteligência Fiscal", layout="wide")

st.title("📊 Consolidação Operacional & Inteligência Fiscal do Grupo")
st.caption("Visão Integrada: RTX Imports, BRT Serviços, BRA, BG, MCR e Filiais")

# --- SEÇÃO 1: ESTRUTURA E EMPRESAS DO GRUPO ---
st.subheader("🏢 Estrutura Societária e Papéis Tributários")

col_emp1, col_emp2, col_emp3 = st.columns(3)

with col_emp1:
    st.info("**RTX IMPORTS COMERCIAL LTDA**\n\n"
            "- **CNPJ Matriz:** 55.175.101/0001-95 (Pouso Alegre/MG)\n"
            "- **Regime:** Lucro Presumido / Real (TTS Importação MG)\n"
            "- **Função:** Importação direta com diferimento de ICMS e distribuição *Intercompany*.")

with col_emp2:
    st.warning("**BRT SERVIÇOS E COMÉRCIO LTDA**\n\n"
               "- **CNPJ Matriz:** 48.768.390/0001-70 (Barueri/SP)\n"
               "- **Regime:** Prestação de Serviços / Apoio\n"
               "- **Função:** Centralização de Mão de Obra e Folha de Pagamento (Rateio de Custos).")

with col_emp3:
    st.success("**BRA / BG / MCR ADESIVOS & FILIAIS**\n\n"
               "- **CNPJs:** Matrizes e Filiais (SP/MG)\n"
               "- **Regime:** Lucro Presumido / Real\n"
               "- **Função:** Venda final no e-commerce/marketplaces e gestão de estoque avançado.")

st.markdown("---")

# --- SEÇÃO 2: SIMULADOR DE OPERAÇÃO INTERCOMPANY & FLUXO FISCAL ---
st.subheader("🔄 Módulo de Análise e Transfer Pricing Intercompany")

col_input1, col_input2, col_input3 = st.columns(3)

with col_input1:
    faturamento_rtx = st.number_input("Vendas/Transferências da RTX (R$)", value=500000.0, step=10000.0)
with col_input2:
    custo_folha_brt = st.number_input("Custo de Pessoal BRT Serviços (R$)", value=45000.0, step=5000.0)
with col_input3:
    margem_intercompany = st.slider("Margem de Lucro RTX para Distribuidoras (%)", 5, 30, 15)

# Cálculos Simulados
valor_venda_distribuidores = faturamento_rtx * (1 + (margem_intercompany / 100))
economia_icms_tts = faturamento_rtx * 0.12  # Estimativa de diferimento/crédito presumido de ICMS no TTS MG

col_m1, col_m2, col_m3, col_m4 = st.columns(4)
col_m1.metric("Importações / Vendas RTX", f"R$ {faturamento_rtx:,.2f}")
col_m2.metric("Repasse Folha (BRT ➔ RTX)", f"R$ {custo_folha_brt:,.2f}")
col_m3.metric("Faturamento Distribuidores", f"R$ {valor_venda_distribuidores:,.2f}")
col_m4.metric("Ganho Estimado TTS MG (ICMS)", f"R$ {economia_icms_tts:,.2f}", delta="Diferimento Ativo")

st.markdown("---")

# --- SEÇÃO 3: AUDITORIA CONTÁBIL & CPCs ---
st.subheader("🚨 Diagnósticos de Conformidade e Normas Contábeis (CPC / Reforma Tributária)")

col_diag1, col_diag2 = st.columns(2)

with col_diag1:
    st.subheader("📌 Validação CPC 30 / NBC TG 47 (Receitas)")
    st.write("""
    - **Corte de Receita (Cut-off):** A receita das saídas da RTX para as distribuidoras só deve ser reconhecida no momento da **efetiva transferência de propriedade/saída física** do galpão de MG.
    - **Vendas E-commerce (Cliente Final):** Vendas efetuadas nas pontas (BRA/BG/MCR) via marketplace devem ter a receita diferida até a entrega/postagem da mercadoria.
    """)

with col_diag2:
    st.subheader("⚖️ Rateio Mão de Obra & Reforma Tributária (IBS/CBS)")
    st.write("""
    - **Reembolso BRT ➔ RTX:** O faturamento de serviços da BRT para a RTX deve ser estruturado como **reembolso de custos sem margem de lucro**, evitando incidência desnecessária de PIS/COFINS e ISS sobre a folha.
    - **Atenção Reforma Tributária:** Com a transição do ICMS para o IBS/CBS, benefícios estaduais como o **TTS de Minas Gerais serão unificados**. O planejamento tributário do grupo deve focar em acúmulo de créditos na entrada.
    """)

# Tabela resumo de lançamentos simulados
st.subheader("📋 Tabela Consolidada por Entidade")
df_grupo = pd.DataFrame({
    "Empresa": ["RTX Imports Comercial", "BRT Serviços e Comércio", "BRA / BG / MCR Adesivos"],
    "Papel": ["Importadora / Hub MG", "Gestão de Pessoal / SP", "Vendas E-commerce / SP-MG"],
    "Faturamento Estimado": [f"R$ {faturamento_rtx:,.2f}", f"R$ {custo_folha_brt:,.2f}", f"R$ {valor_venda_distribuidores:,.2f}"],
    "Principais Impostos": ["ICMS (TTS MG), PIS/COFINS Monofásico", "INSS, FGTS, ISS (Prestação)", "ICMS Difal, PIS/COFINS, IRPJ/CSLL"]
})

st.table(df_grupo)
