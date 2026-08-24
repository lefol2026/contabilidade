import streamlit as st
import pandas as pd
import requests
import time
import sqlite3
from datetime import datetime
import calendar

st.set_page_config(page_title="Consolidação Grupo & Tiny ERP", layout="wide")

st.title("📊 Painel Consolidado - Tiny ERP & Inteligência Fiscal")
st.caption("Consulta Otimizada com Banco Local e Seleção Dinâmica de Período")

# --- BANCO DE DADOS LOCAL (SQLITE) ---
DB_FILE = "dados_tiny.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS faturamento (
            empresa TEXT,
            mes INTEGER,
            ano INTEGER,
            qtd_compras INTEGER,
            total_compras REAL,
            qtd_vendas INTEGER,
            total_vendas REAL,
            data_atualizacao TEXT,
            PRIMARY KEY (empresa, mes, ano)
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def salvar_no_banco(empresa, mes, ano, qtd_c, total_c, qtd_v, total_v):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    data_hoje = datetime.now().strftime("%d/%m/%Y %H:%M")
    c.execute('''
        INSERT OR REPLACE INTO faturamento 
        (empresa, mes, ano, qtd_compras, total_compras, qtd_vendas, total_vendas, data_atualizacao)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (empresa, mes, ano, qtd_c, total_c, qtd_v, total_v, data_hoje))
    conn.commit()
    conn.close()

def buscar_do_banco(empresa, mes, ano):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        SELECT qtd_compras, total_compras, qtd_vendas, total_vendas, data_atualizacao 
        FROM faturamento WHERE empresa = ? AND mes = ? AND ano = ?
    ''', (empresa, mes, ano))
    res = c.fetchone()
    conn.close()
    if res:
        return {'qtd_c': res[0], 'total_c': res[1], 'qtd_v': res[2], 'total_v': res[3], 'atualizacao': res[4]}
    return None

# --- BARRA LATERAL: FILTROS DE MÊS E ANO ---
st.sidebar.header("📅 Filtro de Período")

ano_atual = datetime.now().year
mes_atual = datetime.now().month

anos_disponiveis = list(range(2023, ano_atual + 1))
meses_dict = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro"
}

ano_selecionado = st.sidebar.selectbox("Selecione o Ano", anos_disponiveis, index=anos_disponiveis.index(ano_atual))
mes_selecionado = st.sidebar.selectbox("Selecione o Mês", list(meses_dict.keys()), format_func=lambda x: meses_dict[x], index=mes_atual - 1)

primeiro_dia = f"01/{mes_selecionado:02d}/{ano_selecionado}"
ultimo_dia_num = calendar.monthrange(ano_selecionado, mes_selecionado)[1]
ultimo_dia = f"{ultimo_dia_num:02d}/{mes_selecionado:02d}/{ano_selecionado}"

st.sidebar.info(f"📆 **Período Selecionado:**\n{primeiro_dia} até {ultimo_dia}")
st.sidebar.markdown("---")

forcar_sync = st.sidebar.button("🔄 Buscar Dados Atualizados no Tiny")

EMPRESAS = {
    "RTX IMPORTS (Importadora / Hub MG)": {
        "token": "031d36f9e1eb45afbaec8c8a9ca7cd3d21d1974e49eed05e6c97613494175fee",
        "aliq_imposto": 0.06,
        "regime": "Lucro Presumido / TTS Importação"
    },
    "BRA ADESIVOS (M C R Totti LTDA)": {
        "token": "028e0a127dd20018e5c58cd3deac3b1c52d008fc7556da907f4844f2b35f9014",
        "aliq_imposto": 0.1132,
        "regime": "Lucro Presumido"
    },
    "BG ADESIVOS (BG Adesivos LTDA)": {
        "token": "d8d3b4f28ffde1f20dfcc9351f70b02e3ba53537465c2bc43bb0821b442197fa",
        "aliq_imposto": 0.1132,
        "regime": "Lucro Presumido"
    },
    "BW ADESIVOS (B R Totti LTDA)": {
        "token": "a38cdbdb2b01b3aec71a4392d9aea173926343db673d23c30261854e58d3e992",
        "aliq_imposto": 0.1132,
        "regime": "Lucro Presumido"
    }
}

# --- CONSULTAS NA API (SEM CACHE ESTÁTICO DENTRO DA FUNÇÃO) ---
def consultar_vendas_api(token, d_inicio, d_fim):
    url = "https://api.tiny.com.br/api2/pedidos.pesquisa.php"
    payload = {'token': token, 'formato': 'json', 'data_inicial': d_inicio, 'data_final': d_fim}
    try:
        res = requests.post(url, data=payload, headers={'User-Agent': 'Mozilla/5.0'}, timeout=12).json()
        if res.get('retorno', {}).get('status') == 'OK':
            pedidos = res['retorno'].get('pedidos', [])
            return {'qtd': len(pedidos), 'total': sum(float(p['pedido']['valor']) for p in pedidos if 'pedido' in p)}
    except Exception:
        pass
    return {'qtd': 0, 'total': 0.0}

def consultar_compras_api(token, d_inicio, d_fim):
    url = "https://api.tiny.com.br/api2/notas.fiscais.pesquisa.php"
    payload = {'token': token, 'formato': 'json', 'data_inicial': d_inicio, 'data_final': d_fim, 'tipo': 'E'}
    try:
        res = requests.post(url, data=payload, headers={'User-Agent': 'Mozilla/5.0'}, timeout=12).json()
        if res.get('retorno', {}).get('status') == 'OK':
            notas = res['retorno'].get('notas_fiscais', [])
            return {'qtd': len(notas), 'total': sum(float(n['nota_fiscal']['valor_nota']) for n in notas if 'nota_fiscal' in n)}
    except Exception:
        pass
    return {'qtd': 0, 'total': 0.0}

# --- PROCESSAMENTO PRINCIPAL ---
st.subheader(f"🔄 Balanço de Compras vs Vendas — {meses_dict[mes_selecionado]}/{ano_selecionado}")

resultados = []
total_vendas_grupo = 0.0
total_compras_grupo = 0.0
total_impostos_grupo = 0.0

for nome_empresa, info in EMPRESAS.items():
    dados_locais = buscar_do_banco(nome_empresa, mes_selecionado, ano_selecionado)
    
    if not dados_locais or forcar_sync:
        res_v = consultar_vendas_api(info['token'], primeiro_dia, ultimo_dia)
        time.sleep(0.3)
        res_c = consultar_compras_api(info['token'], primeiro_dia, ultimo_dia)
        time.sleep(0.3)
        
        salvar_no_banco(nome_empresa, mes_selecionado, ano_selecionado, res_c['qtd'], res_c['total'], res_v['qtd'], res_v['total'])
        vendas, compras, qtd_v, qtd_c = res_v['total'], res_c['total'], res_v['qtd'], res_c['qtd']
        status_origem = "⚡ Atualizado via API"
    else:
        vendas = dados_locais['total_v']
        compras = dados_locais['total_c']
        qtd_v = dados_locais['qtd_v']
        qtd_c = dados_locais['qtd_c']
        status_origem = f"💾 Banco Local ({dados_locais['atualizacao']})"

    impostos = vendas * info['aliq_imposto']
    total_vendas_grupo += vendas
    total_compras_grupo += compras
    total_impostos_grupo += impostos
    
    resultados.append({
        "Empresa": nome_empresa,
        "Regime Fiscal": info['regime'],
        "Origem": status_origem,
        "NFs Entrada": qtd_c,
        "Total Comprado (Entradas)": f"R$ {compras:,.2f}",
        "Qtd Vendas": qtd_v,
        "Total Vendido (Saídas)": f"R$ {vendas:,.2f}",
        "Resultado Bruto": f"R$ {(vendas - compras):,.2f}",
        "Impostos Est.": f"R$ {impostos:,.2f}"
    })

# MÉTRICAS RESUMO
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Entradas (Compras/DI)", f"R$ {total_compras_grupo:,.2f}")
c2.metric("Total Saídas (Vendas)", f"R$ {total_vendas_grupo:,.2f}")
c3.metric("Resultado Operacional", f"R$ {(total_vendas_grupo - total_compras_grupo):,.2f}")
c4.metric("Impostos Consolidados Est.", f"R$ {total_impostos_grupo:,.2f}")

st.markdown("---")
df_resultado = pd.DataFrame(resultados)
st.dataframe(df_resultado, use_container_width=True)
