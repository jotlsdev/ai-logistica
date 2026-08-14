import streamlit as st
from py3dbp import Packer, Bin, Item
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd

# ==========================================
# 1. CONFIGURAÇÃO E BANCO DE DADOS (FIREBASE)
# ==========================================
st.set_page_config(page_title="Logística ERP", page_icon="📦", layout="wide")
st.title("📦 Sistema de Empacotamento")

# Conectando ao Firebase puxando as chaves do cofre da nuvem
if not firebase_admin._apps:
    cred_dict = dict(st.secrets["firebase"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- Funções para Ler e Salvar no Firebase ---
def obter_produtos():
    produtos_ref = db.collection('produtos').stream()
    produtos = {}
    for doc in produtos_ref:
        produtos[doc.id] = doc.to_dict()
    return produtos

def obter_caixas():
    caixas_ref = db.collection('caixas').stream()
    caixas = []
    for doc in caixas_ref:
        dados = doc.to_dict()
        dados['id'] = doc.id
        caixas.append(dados)
    return caixas

def salvar_produto(nome, w, h, d, peso):
    db.collection('produtos').document(nome).set({"w": w, "h": h, "d": d, "peso": peso})

def salvar_caixa(nome, w, h, d, peso_max):
    db.collection('caixas').document(nome).set({"w": w, "h": h, "d": d, "peso_max": peso_max})

# ==========================================
# 2. FUNÇÃO DO CÁLCULO MATEMÁTICO (3D)
# ==========================================
def calcular_melhor_caixa(itens_solicitados):
    banco_caixas = obter_caixas()
    banco_produtos = obter_produtos()
    
    caixas_ordenadas = sorted(banco_caixas, key=lambda c: c['w'] * c['h'] * c['d'])
    
    for caixa in caixas_ordenadas:
        packer = Packer()
        packer.add_bin(Bin(caixa['id'], caixa['w'], caixa['h'], caixa['d'], caixa['peso_max']))
        
        peso_total = 0
        for item in itens_solicitados:
            nome = item['nome']
            qtd = item['quantidade']
            
            if nome in banco_produtos:
                prod = banco_produtos[nome]
                for i in range(qtd):
                    packer.add_item(Item(f"{nome}_{i}", prod['w'], prod['h'], prod['d'], prod['peso']))
                    peso_total += prod['peso']
            else:
                return f"Produto '{nome}' não encontrado!", 0
        
        packer.pack()
        
        for b in packer.bins:
            if len(b.unfitted_items) == 0: 
                return b.name, peso_total
                
    return "Nenhuma das caixas cadastradas é grande o suficiente!", 0

# ==========================================
# 3. ÁREA ADMINISTRATIVA (MENU LATERAL)
# ==========================================
with st.sidebar:
    st.header("⚙️ Cadastro em Massa")
    st.divider()
    
    st.subheader("📁 Caixas")
    st.info("Colunas: NOME, W, H, D, PESO_MAX")
    arquivo_caixas = st.file_uploader("Planilha de Caixas (.xlsx)", type=["xlsx"])
    if arquivo_caixas:
        df = pd.read_excel(arquivo_caixas)
        if st.button("☁️ Salvar Caixas", use_container_width=True):
            with st.spinner("Gravando..."):
                for index, linha in df.iterrows():
                    salvar_caixa(str(linha['NOME']), float(linha['W']), float(linha['H']), float(linha['D']), float(linha['PESO_MAX']))
                st.success("✅ Caixas salvas!")
                st.rerun()

    st.divider()
    
    st.subheader("🛒 Produtos")
    st.info("Colunas: NOME, W, H, D, PESO")
    arquivo_produtos = st.file_uploader("Planilha de Produtos (.xlsx)", type=["xlsx"], key="prod")
    if arquivo_produtos:
        df_prod = pd.read_excel(arquivo_produtos)
        if st.button("☁️ Salvar Produtos", use_container_width=True):
            with st.spinner("Gravando..."):
                for index, linha in df_prod.iterrows():
                    salvar_produto(str(linha['NOME']), float(linha['W']), float(linha['H']), float(linha['D']), float(linha['PESO']))
                st.success("✅ Produtos salvos!")
                st.rerun()

# ==========================================
# 4. INTERFACE PRINCIPAL (CALCULADORA)
# ==========================================
# Variável temporária para guardar os itens que o usuário quer calcular
if 'pedido_atual' not in st.session_state:
    st.session_state.pedido_atual = []

produtos_atuais = obter_produtos()
nomes_dos_produtos = list(produtos_atuais.keys())

st.subheader("📋 Novo Pedido / Cálculo de Caixa")

if not nomes_dos_produtos:
    st.warning("Nenhum produto cadastrado no banco de dados. Faça o upload da planilha primeiro.")
else:
    # Linha para adicionar itens ao pedido
    col1, col2, col3 = st.columns([3, 1, 1])
    
    with col1:
        produto_selecionado = st.selectbox("Código / Nome do Produto", options=nomes_dos_produtos)
    with col2:
        quantidade = st.number_input("Quantidade", min_value=1, value=1, step=1)
    with col3:
        st.write("") # Espaçamento para alinhar o botão com os campos de texto
        st.write("")
        if st.button("➕ Adicionar à lista", use_container_width=True):
            st.session_state.pedido_atual.append({"nome": produto_selecionado, "quantidade": quantidade})
            st.rerun()

    st.divider()

    # Mostra a lista de itens e o botão de calcular
    if st.session_state.pedido_atual:
        st.write("### Itens a empacotar:")
        
        # Transforma a lista num formato bonito para mostrar na tela
        df_pedido = pd.DataFrame(st.session_state.pedido_atual)
        st.table(df_pedido)
        
        col_calc, col_limpar = st.columns([1, 1])
        
        with col_calc:
            if st.button("📦 Calcular Embalagem Ideal", type="primary", use_container_width=True):
                with st.spinner("Calculando o empacotamento 3D..."):
                    caixa_ideal, peso_total = calcular_melhor_caixa(st.session_state.pedido_atual)
                    
                    if peso_total > 0:
                        st.success(f"**Recomendação:** Use a {caixa_ideal}")
                        st.info(f"**Peso Bruto Estimado:** {peso_total/1000:.2f} kg")
                    else:
                        st.error(caixa_ideal)
        
        with col_limpar:
            if st.button("🗑️ Limpar Pedido", use_container_width=True):
                st.session_state.pedido_atual = []
                st.rerun()
