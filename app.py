import os
import pandas as pd
import streamlit as st

DATA_FILE = "dados_consolidados.parquet"

# ==========================================
# 1. CONFIGURAÇÃO DA PÁGINA & CSS
# ==========================================
st.set_page_config(
    page_title="Executive B.I. - Auditoria Fiscal",
    page_icon="👑",
    layout="wide",
)

st.markdown(
    """
    <style>
    .kpi-card {
        background: #ffffff;
        border: 1px solid #e0e0e0;
        border-radius: 8px;
        padding: 10px 12px;
        box-shadow: 0px 2px 4px rgba(0,0,0,0.05);
        height: 130px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .kpi-title { font-size: 0.72rem; font-weight: 700; color: #555; text-transform: uppercase; }
    .kpi-value { font-size: 1.25rem; font-weight: 800; color: #111; white-space: nowrap; }
    .kpi-sub { font-size: 0.70rem; color: #00875A; font-weight: 600; }
    </style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# 2. PARÂMETROS TRIBUTÁRIOS
# ==========================================
EMPRESAS_CONFIG = {
    "MCRTOTTI LTDA / BRA": {
        "icms": 0.06,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
    },
    "BR TOTTI LTDA / BW": {
        "icms": 0.06,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
    },
    "RTX IMPORTS COMERCIAL LTDA": {
        "icms": 0.06,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
    },
    "BG ADESIVOS LTDA": {
        "icms": 0.0439,
        "pis": 0.0065,
        "cofins": 0.0300,
        "irpj": 0.0120,
        "csll": 0.0108,
    },
}


def fmt_moeda(val):
    if abs(val) >= 1_000_000:
        return f"R$ {val/1_000_000:,.2f} Mi"
    elif abs(val) >= 1_000:
        return f"R$ {val/1_000:,.1f} K"
    return f"R$ {val:,.2f}"


def fmt_brl(val):
    return (
        f"R$ {val:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    )


st.title("👑 Executive B.I. — Apuração Fiscal & Conciliação")


# ==========================================
# 3. LEITURA INSTANTÂNEA DOS DADOS
# ==========================================
@st.cache_data
def carregar_dados_locais():
    if os.path.exists(DATA_FILE):
        return pd.read_parquet(DATA_FILE)
    return pd.DataFrame()


df_raw = carregar_dados_locais()

# ==========================================
# 4. DASHBOARD E FILTROS
# ==========================================
if not df_raw.empty:
    st.markdown("### 🏢 Empresa:")
    empresas_opcoes = ["TODAS AS EMPRESAS (GRUPO)"] + list(
        EMPRESAS_CONFIG.keys()
    )
    empresa_sel = st.radio(
        "Empresa:",
        empresas_opcoes,
        horizontal=True,
        label_visibility="collapsed",
        key="radio_emp",
    )

    st.markdown("### 📅 Mês:")
    meses_opcoes = ["Consolidado Anual"] + sorted(list(df_raw["Mês"].unique()))
    mes_sel = st.radio(
        "Mês:",
        meses_opcoes,
        horizontal=True,
        label_visibility="collapsed",
        key="radio_mes",
    )

    df_filtrado = df_raw.copy()
    if empresa_sel != "TODAS AS EMPRESAS (GRUPO)":
        df_filtrado = df_filtrado[df_filtrado["Empresa"] == empresa_sel]
    if mes_sel != "Consolidado Anual":
        df_filtrado = df_filtrado[df_filtrado["Mês"] == mes_sel]

    df_vendas = df_filtrado[df_filtrado["Tipo Operacao"] == "Venda (Saida)"]
    fat_bruto = df_vendas["Valor"].sum()
    compras_tot = df_filtrado[
        df_filtrado["Tipo Operacao"] == "Compra (Entrada)"
    ]["Valor"].sum()

    icms, piscofins, irpjcsll = 0.0, 0.0, 0.0
    for _, row in df_vendas.iterrows():
        emp = row["Empresa"]
        v = row["Valor"]
        if emp in EMPRESAS_CONFIG:
            cfg = EMPRESAS_CONFIG[emp]
            icms += v * cfg["icms"]
            piscofins += v * (cfg["pis"] + cfg["cofins"])
            irpjcsll += v * (cfg["irpj"] + cfg["csll"])

    tot_impostos = icms + piscofins + irpjcsll
    aliquota_efetiva = (
        (tot_impostos / fat_bruto * 100) if fat_bruto > 0 else 0.0
    )

    st.markdown("---")
    c1, c2, c3, c4, c5, c6 = st.columns(6)

    with c1:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">💰'
            f' FATURAMENTO</div><div'
            f' class="kpi-value">{fmt_moeda(fat_bruto)}</div><div'
            f' class="kpi-sub">{fmt_brl(fat_bruto)}</div></div>',
            unsafe_allow_html=True,
        )
    with c2:
        st.markdown(
            f'<div class="kpi-card" style="border-left: 4px solid'
            ' #2E7D32;"><div class="kpi-title">🛒 COMPRAS</div><div'
            f' class="kpi-value">{fmt_moeda(compras_tot)}</div><div'
            ' class="kpi-sub" style="color:'
            f' #2E7D32;">{fmt_brl(compras_tot)}</div></div>',
            unsafe_allow_html=True,
        )
    with c3:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">🏛️ ICMS'
            f' TTS</div><div class="kpi-value">{fmt_moeda(icms)}</div><div'
            ' class="kpi-sub">'
            f'{(icms/fat_bruto*100 if fat_bruto>0 else 0):.2f}% receita</div></div>',
            unsafe_allow_html=True,
        )
    with c4:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">📊 PIS /'
            ' COFINS</div><div'
            f' class="kpi-value">{fmt_moeda(piscofins)}</div><div'
            ' class="kpi-sub">3.65% Cumulativo</div></div>',
            unsafe_allow_html=True,
        )
    with c5:
        st.markdown(
            f'<div class="kpi-card"><div class="kpi-title">⚖️ IRPJ /'
            ' CSLL</div><div'
            f' class="kpi-value">{fmt_moeda(irpjcsll)}</div><div'
            ' class="kpi-sub">2.28% Presumido</div></div>',
            unsafe_allow_html=True,
        )
    with c6:
        st.markdown(
            f'<div class="kpi-card" style="border-left: 4px solid'
            ' #D32F2F;"><div class="kpi-title">🚨 TOTAL IMPOSTOS</div><div'
            f' class="kpi-value">{fmt_moeda(tot_impostos)}</div><div'
            ' class="kpi-sub" style="color: #D32F2F;">Carga:'
            f" {aliquota_efetiva:.2f}%</div></div>",
            unsafe_allow_html=True,
        )

    st.markdown("---")

    t1, t2, t3, t4 = st.tabs([
        "📈 DRE & Tendências",
        "🔍 Conciliação (Livro vs Drive)",
        "🏢 Por Empresa",
        "📋 Auditoria",
    ])

    with t1:
        g1, g2 = st.columns([2, 1])
        with g1:
            st.markdown(f"**Operacional Mês a Mês ({empresa_sel})**")
            df_chart_base = (
                df_raw
                if empresa_sel == "TODAS AS EMPRESAS (GRUPO)"
                else df_raw[df_raw["Empresa"] == empresa_sel]
            )
            df_v = (
                df_chart_base[df_chart_base["Tipo Operacao"] == "Venda (Saida)"]
                .groupby("Mês")["Valor"]
                .sum()
                .rename("Vendas")
            )
            df_c = (
                df_chart_base[
                    df_chart_base["Tipo Operacao"] == "Compra (Entrada)"
                ]
                .groupby("Mês")["Valor"]
                .sum()
                .rename("Compras")
            )
            st.bar_chart(pd.concat([df_v, df_c], axis=1).fillna(0))
        with g2:
            st.markdown(f"**Sintético Impostos ({mes_sel})**")
            df_t = pd.DataFrame({
                "Imposto": ["ICMS TTS", "PIS/COFINS", "IRPJ/CSLL"],
                "Valor": [icms, piscofins, irpjcsll],
            }).set_index("Imposto")
            st.bar_chart(df_t, color="#FF8F00")

    with t2:
        st.subheader("🔍 Confronto: Livro Fiscal vs. Google Drive / ERP")
        df_conc = (
            df_filtrado.groupby(["Mês", "Origem"])["Valor"]
            .sum()
            .unstack(fill_value=0)
        )
        if "Livro Fiscal" not in df_conc.columns:
            df_conc["Livro Fiscal"] = 0.0
        if "NFs / Drive" not in df_conc.columns:
            df_conc["NFs / Drive"] = 0.0
        df_conc["Divergência (R$)"] = (
            df_conc["Livro Fiscal"] - df_conc["NFs / Drive"]
        )
        st.dataframe(
            df_conc.style.format("R$ {:,.2f}"), use_container_width=True
        )
        st.bar_chart(df_conc[["Livro Fiscal", "NFs / Drive"]])

    with t3:
        st.markdown("**Faturamento por Empresa**")
        df_e = (
            df_filtrado[df_filtrado["Tipo Operacao"] == "Venda (Saida)"]
            .groupby("Empresa")["Valor"]
            .sum()
            .reset_index()
        )
        st.bar_chart(df_e.set_index("Empresa")["Valor"], color="#43A047")

    with t4:
        st.dataframe(
            df_filtrado[[
                "Arquivo",
                "Origem",
                "Mês",
                "Empresa",
                "Tipo Operacao",
                "Valor",
            ]],
            use_container_width=True,
        )

else:
    st.warning(
        "⚠️ O arquivo `dados_consolidados.parquet` ainda não foi gerado!"
        " Execute primeiro o comando `python gerar_base.py` no terminal da sua"
        " máquina."
    )
