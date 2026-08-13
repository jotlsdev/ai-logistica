import streamlit as st
from py3dbp import Packer, Bin, Item
import google.generativeai as genai
import json
import re
import firebase_admin
import pandas as pd
from firebase_admin import credentials, firestore

# ==========================================
# 1. CONFIGURAÇÃO E BANCO DE DADOS (FIREBASE)
# ==========================================
st.set_page_config(page_title="Logística AI na Nuvem", page_icon="☁️")
st.title("☁️ IA para Empacotamento (Firebase)")

# Puxando a chave do Gemini do cofre da nuvem
API_KEY = st.secrets["GEMINI_API_KEY"]

# Conectando ao Firebase puxando as chaves do cofre da nuvem
if not firebase_admin._apps:
    cred_dict = dict(st.secrets["firebase"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# --- Novas Funções para Ler e Salvar no Firebase ---

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
    # O Firestore cria a coleção 'produtos' e o documento automaticamente
    db.collection('produtos').document(nome).set({
        "w": w, "h": h, "d": d, "peso": peso
    })

def salvar_caixa(nome, w, h, d, peso_max):
    db.collection('caixas').document(nome).set({
        "w": w, "h": h, "d": d, "peso_max": peso_max
    })

st.divider()
st.subheader("📁 Cadastro em Massa via Planilha")
st.info("A planilha deve ter as colunas exatas: NOME, W, H, D, PESO_MAX")

arquivo_excel = st.file_uploader("Arraste sua planilha (.xlsx) aqui", type=["xlsx"])

if arquivo_excel is not None:
    # O Pandas lê a planilha transformada em tabela
    df = pd.read_excel(arquivo_excel)
    st.dataframe(df) # Mostra uma prévia na tela
    
    if st.button("☁️ Salvar tudo no Firebase"):
        with st.spinner("Salvando caixas no banco de dados..."):
            for index, linha in df.iterrows():
                # Envia cada linha direto para o Firebase, ignorando a IA
                salvar_caixa(
                    str(linha['NOME']), 
                    float(linha['W']), 
                    float(linha['H']), 
                    float(linha['D']), 
                    float(linha['PESO_MAX'])
                )
            st.success("✅ Todas as caixas foram cadastradas instantaneamente!")
            st.rerun()

# ==========================================
# 2. FUNÇÃO DA INTELIGÊNCIA ARTIFICIAL
# ==========================================
def processar_chat_ia(mensagem, lista_produtos_disponiveis):
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel('gemini-3.5-flash')
    
    prompt = f"""
    Você é um assistente logístico. Analise a mensagem do usuário e decida a ação.
    
    Ações possíveis:
    1. "cadastrar_produto": Extraia: nome, w (largura cm), h (altura cm), d (profundidade cm), peso (em gramas).
    2. "cadastrar_caixa": Extraia: nome, w, h, d, peso_max (em gramas).
    3. "calcular": Extraia os produtos e as quantidades solicitadas. Produtos disponíveis: {lista_produtos_disponiveis}.
    
    Mensagem do usuário: "{mensagem}"
    
    REGRA ESTRITA: Responda APENAS com o JSON, usando exatamente um destes formatos:
    Se for cadastro: {{"acao": "cadastrar_produto", "dados": {{"nome": "caderno", "w": 20, "h": 2, "d": 28, "peso": 500}}}}
    Se for cálculo: {{"acao": "calcular", "dados": [{{"nome": "caneca", "quantidade": 2}}]}}
    """
    
    try:
        resposta = model.generate_content(prompt)
        match = re.search(r'\{.*\}', resposta.text, re.DOTALL)
        
        if match:
            return json.loads(match.group(0))
        else:
            st.error(f"Formato inválido. IA respondeu: {resposta.text}")
            return None
    except Exception as e:
        st.error(f"Erro no processamento: {e}")
        return None

# ==========================================
# 3. FUNÇÃO DO CÁLCULO MATEMÁTICO (3D)
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
            nome = item['nome'].lower()
            qtd = item['quantidade']
            
            if nome in banco_produtos:
                prod = banco_produtos[nome]
                for i in range(qtd):
                    packer.add_item(Item(f"{nome}_{i}", prod['w'], prod['h'], prod['d'], prod['peso']))
                    peso_total += prod['peso']
            else:
                return f"Produto '{nome}' não encontrado no banco de dados!", 0
        
        packer.pack()
        
        for b in packer.bins:
            if len(b.unfitted_items) == 0: 
                return b.name, peso_total
                
    return "Nenhuma das caixas cadastradas é grande o suficiente!", 0

# ==========================================
# 4. INTERFACE DO USUÁRIO
# ==========================================
# Carregamos os dados em tempo real da nuvem
caixas_atuais = obter_caixas()
produtos_atuais = obter_produtos()

col1, col2 = st.columns(2)
with col1:
    st.write("📦 **Caixas (Nuvem):**")
    if not caixas_atuais:
        st.warning("Nenhuma caixa cadastrada ainda.")
    else:
        st.json(caixas_atuais)
with col2:
    st.write("🛒 **Produtos (Nuvem):**")
    if not produtos_atuais:
        st.warning("Nenhum produto cadastrado ainda.")
    else:
        st.json(produtos_atuais)

st.divider()

# ==========================================
# ÁREA ADMINISTRATIVA (MENU LATERAL)
# ==========================================
with st.sidebar:
    st.header("⚙️ Administração")
    st.divider()
    st.subheader("📁 Cadastro em Massa (Caixas)")
    st.info("Colunas obrigatórias na planilha: NOME, W, H, D, PESO_MAX")

    arquivo_excel = st.file_uploader("Envie sua planilha (.xlsx)", type=["xlsx"])

    if arquivo_excel is not None:
        # Lê a planilha
        df = pd.read_excel(arquivo_excel)
        st.dataframe(df, use_container_width=True) # Mostra miniatura da tabela
        
        if st.button("☁️ Salvar no Firebase", use_container_width=True):
            with st.spinner("Gravando no banco de dados..."):
                for index, linha in df.iterrows():
                    salvar_caixa(
                        str(linha['NOME']), 
                        float(linha['W']), 
                        float(linha['H']), 
                        float(linha['D']), 
                        float(linha['PESO_MAX'])
                    )
                st.success("✅ Caixas cadastradas com sucesso!")

mensagem_usuario = st.chat_input("Fale com a IA (Ex: Cadastre uma caixa G de 50x40x50 pesando max 10000g)")

if mensagem_usuario:
    st.chat_message("user").write(mensagem_usuario)
    
    with st.spinner("🤖 Sincronizando com a nuvem e processando..."):
        nomes_produtos = list(produtos_atuais.keys())
        resposta_ia = processar_chat_ia(mensagem_usuario, nomes_produtos)
        
        if resposta_ia:
            acao = resposta_ia.get("acao")
            dados = resposta_ia.get("dados")
            
            if acao == "cadastrar_produto":
                nome_prod = dados["nome"].lower()
                salvar_produto(nome_prod, dados["w"], dados["h"], dados["d"], dados["peso"])
                st.chat_message("assistant").success(f"✅ Produto '{nome_prod}' salvo no Firebase!")
                st.rerun()
                
            elif acao == "cadastrar_caixa":
                nome_caixa = dados["nome"]
                salvar_caixa(nome_caixa, dados["w"], dados["h"], dados["d"], dados["peso_max"])
                st.chat_message("assistant").success(f"✅ Caixa '{nome_caixa}' salva no Firebase!")
                st.rerun()
                
            elif acao == "calcular":
                caixa_ideal, peso_total = calcular_melhor_caixa(dados)
                if peso_total > 0:
                    st.chat_message("assistant").success(f"📦 **Use a {caixa_ideal}**")
                    st.chat_message("assistant").info(f"⚖️ **Peso total estimado:** {peso_total/1000} kg")
                else:
                    st.chat_message("assistant").error(caixa_ideal)
