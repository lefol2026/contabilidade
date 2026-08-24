import streamlit as st
import pandas as pd
import requests
import time
from datetime import datetime
import calendar

st.set_page_config(page_title="Consolidação Grupo & Tiny ERP", layout="wide")

st.title("📊 Painel Consolidado - Tiny ERP & Inteligência Fiscal")
st.caption("Consulta em Tempo Real com Filtros de Período Corrigidos")

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

# Datas formatadas para a API
primeiro_dia = f"01/{mes_selecionado:02d}/{ano_selecionado}"
ultimo_dia_num = calendar.monthrange(ano_selecionado, mes_selecionado)[1]
ultimo_dia = f"{ultimo_dia_num:02d}/{mes_selecionado:02d}/{ano_selecionado}"

st.sidebar.info(f"📆 **Período Selecionado:**\n{primeiro_dia} até {ultimo_dia}")

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

# --- CONSULTA DE VENDAS (PEDIDOS) ---
def consultar_vendas_tiny(token, d_inicio, d_fim):
    url = "https://api.tiny.com.br/api2/pedidos.pesquisa.php"
    payload = {
        'token': token,
        'formato': 'json',
        'data_inicial': d_inicio,
        'data_final': d_fim
    }
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.post(url, data=payload, headers=headers, timeout=12)
        dados = response.json()
        retorno = dados.get('retorno', {})
        
        if retorno.get('status') == 'OK':
            pedidos = retorno.get('pedidos', [])
            total = sum(float(p['pedido']['valor']) for p in pedidos if 'pedido' in p)
            return {'qtd': len(pedidos), 'total': total, 'status': '🟢 Conectado'}
        elif retorno.get('status') == 'ERRO':
            erros = retorno.get('erros', [{}])
            msg = erros[0].get('erro', 'Sem dados')
            return {'qtd': 0, 'total': 0.0, 'status': f'🟡 {msg}'}
    except Exception as e:
        return {'qtd': 0, 'total': 0.0, 'status': '🔴 Erro Conexão'}
    
    return {'qtd': 0, 'total': 0.0, 'status': '⚪ Sem Pedidos'}

# --- CONSULTA DE COMPRAS (NOTAS FISCAIS DE ENTRADA) ---
def consultar_compras_tiny(token, d_inicio, d_fim):
    url = "https://api.tiny.com.br/api2/notas.fiscais.pesquisa.php"
    payload = {
        'token': token,
        'formato': 'json',
        'data_inicial': d_inicio,
        'data_final': d_fim,
        'tipo': 'E'
    }
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.post(url, data=payload, headers=headers, timeout=12)
        dados = response.json()
        retorno = dados.get('retorno', {})
        
        if retorno.get('status') == 'OK':
            notas = retorno.get('notas_fiscais', [])
            total = sum(float(n['nota_fiscal']['valor_nota']) for n in notas if 'nota_fiscal' in n)
            return {'qtd': len(notas), 'total': total}
    except Exception:
        pass
        
    return {'qtd': 0, 'total': 0.0}

# --- EXIBIÇÃO PRINCIPAL ---
st.subheader(f"🔄 Balanço Consolidado — {meses_dict[mes_selecionado]}/{ano_selecionado}")

resultados = []
total_vendas_grupo = 0.0
total_compras_grupo = 0.0
total_impostos_grupo = 0.0

for nome_empresa, info in EMPRESAS.items():
    res_vendas = consultar_vendas_tiny(info['token'], primeiro_dia, ultimo_dia)
    time.sleep(0.4) # Intervalo para evitar rejeição da API
    
    res_compras = consultar_compras_tiny(info['token'], primeiro_dia, ultimo_dia)
    time.sleep(0.4)
    
    vendas = res_vendas['total']
    compras = res_compras['total']
    impostos = vendas * info['aliq_imposto']
    
    total_vendas_grupo += vendas
    total_compras_grupo += compras
    total_impostos_grupo += impostos
    
    resultados.append({
        "Empresa": nome_empresa,
        "Regime Fiscal": info['regime'],
        "Status": res_vendas['status'],
        "NFs Entrada": res_compras['qtd'],
        "Total Comprado (Entradas)": f"R$ {compras:,.2f}",
        "Qtd Vendas": res_vendas['qtd'],
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
