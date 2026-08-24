import streamlit as st
import pandas as pd
import requests

st.set_page_config(page_title="Consolidação Grupo & Integration Tiny ERP", layout="wide")

st.title("📊 Painel Consolidado - Tiny ERP & Inteligência Fiscal")
st.caption("Consulção em Tempo Real: RTX Imports, BRA, BG e BW (B R Totti)")

# --- CONFIGURAÇÃO DOS TOKENS DAS EMPRESAS ---
EMPRESAS = {
    "RTX IMPORTS (Importadora / Hub MG)": {
        "token": "031d36f9e1eb45afbaec8c8a9ca7cd3d21d1974e49eed05e6c97613494175fee",
        "aliq_imposto": 0.06,  # Estimativa ICMS TTS/MG + PIS/COFINS
        "regime": "Lucro Presumido / TTS Importação"
    },
    "BRA ADESIVOS (M C R Totti LTDA)": {
        "token": "028e0a127dd20018e5c58cd3deac3b1c52d008fc7556da907f4844f2b35f9014",
        "aliq_imposto": 0.1132,  # PIS/COFINS (3.65%) + ICMS/Outros
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

# --- FUNÇÃO DE CONSULTA NA API DO TINY ERP ---
def consultar_tiny(token):
    url = "https://api.tiny.com.br/api2/pedidos.pesquisa.php"
    payload = {
        'token': token,
        'formato': 'json'
    }
    try:
        response = requests.post(url, data=payload, timeout=10)
        dados = response.json()
        retorno = dados.get('retorno', {})
        
        if retorno.get('status') == 'OK':
            pedidos = retorno.get('pedidos', [])
            total_vendas = sum(float(p['pedido']['valor']) for p in pedidos if 'pedido' in p)
            return {'status': '🟢 Conectado', 'qtd': len(pedidos), 'total': total_vendas, 'erro': None}
        else:
            erros = retorno.get('erros', [{}])
            msg_erro = erros[0].get('erro', 'Erro desconhecido na API')
            return {'status': '🔴 Erro na API', 'qtd': 0, 'total': 0.0, 'erro': msg_erro}
    except Exception as e:
        return {'status': '🔴 Erro Conexão', 'qtd': 0, 'total': 0.0, 'erro': str(e)}

# --- PROCESSAMENTO DOS DADOS ---
st.subheader("🔄 Faturamento & Apuração de Impostos (Base Tiny ERP)")

resultados = []
total_grupo_vendas = 0.0
total_grupo_impostos = 0.0

for nome_empresa, info in EMPRESAS.items():
    res = consultar_tiny(info['token'])
    vendas = res['total']
    impostos = vendas * info['aliq_imposto']
    
    total_grupo_vendas += vendas
    total_grupo_impostos += impostos
    
    resultados.append({
        "Empresa": nome_empresa,
        "Regime Fiscal": info['regime'],
        "Status API": res['status'],
        "Qtd Pedidos": res['qtd'],
        "Faturamento Bruto": f"R$ {vendas:,.2f}",
        "Impostos Est. a Apurar": f"R$ {impostos:,.2f}",
        "Detalhes / Observações": res['erro'] if res['erro'] else "Dados sincronizados com sucesso"
    })

# MÉTIRCAS RESUMO DO GRUPO
c1, c2, c3 = st.columns(3)
c1.metric("Faturamento Consolidado do Grupo", f"R$ {total_grupo_vendas:,.2f}")
c2.metric("Impostos Consolidados a Apurar", f"R$ {total_grupo_impostos:,.2f}")
c3.metric("Empresas Conectadas", f"{len(EMPRESAS)} Unidades")

st.markdown("---")

# TABELA DETALHADA
df_resultado = pd.DataFrame(resultados)
st.dataframe(df_resultado, use_container_width=True)

# --- SEÇÃO DE REGULAMENTAÇÃO TRIBUTÁRIA E CPCS ---
st.subheader("📋 Cruzamento Contábil e Regras de Compliance")

st.markdown("""
* **RTX Imports vs. Distribuidoras (Transfer Pricing):** Verificar a margem aplicada nas vendas intercompany para garantir conformidade com as regras de valoração aduaneira e diferimento de ICMS (TTS/MG).
* **CPC 30 / NBC TG 47:** Garantir que o reconhecimento da receita nas empresas do e-commerce (BRA, BG e BW) coincida com o faturamento/saída informado nas notas fiscais do Tiny ERP.
* **Segregação Monofásica (PIS/COFINS):** Validar se os produtos cadastrados no Tiny possuem o NCM e CST corretos para exclusão de PIS/COFINS nas saídas das distribuidoras.
""")
