import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap
import pdfplumber
import re
from streamlit_js_eval import streamlit_js_eval

# --- SISTEMA DE LOGIN ---
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    
    if not st.session_state["authenticated"]:
        st.title("Acesso Restrito")
        senha = st.text_input("Digite a senha de acesso:", type="password")
        if st.button("Entrar"):
            # O erro anterior foi aqui. A senha PRECISA estar entre aspas.
            if senha == "ft20":  
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Senha incorreta")
        return False
    return True

if not check_password():
    st.stop()

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="FT20 - LTP", layout="wide", page_icon="🦅")

# Cabeçalho com a Identidade: Coruja, Águia, Raio e Trajeto
st.markdown("""
    <div style="text-align: center;">
        <h1 style="color: #d32f2f;">FT20 - LTP 🦉🦅⚡📈</h1>
        <p style="font-size: 1.1em; font-weight: bold;">Location Time Past</p>
        <p style="color: #555;">Inteligência e Patrulhamento Tático</p>
    </div>
    <hr style="border: 1px solid #d32f2f;">
""", unsafe_allow_html=True)

# Captura de Localização (GPS do Celular)
loc = streamlit_js_eval(js_expressions="new Promise((resolve, reject) => { navigator.geolocation.getCurrentPosition(pos => { resolve({lat: pos.coords.latitude, lon: pos.coords.longitude}) }, err => { reject(err) }) })", key="get_location")

# --- PROCESSAMENTO DO SENTRY ---
def extrair_dados_sentry(pdf_file):
    dados = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
            # Padrão para capturar Data e Coordenadas do relatório SESP-MT
            datas = re.findall(r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})', text)
            coords = re.findall(r'(-\d+\.\d+)\s*&\s*(-\d+\.\d+)', text)
            for i in range(min(len(coords), len(datas))):
                dados.append({
                    'data': pd.to_datetime(datas[i], dayfirst=True),
                    'lat': float(coords[i][0]),
                    'lon': float(coords[i][1])
                })
    return pd.DataFrame(dados)

uploaded_file = st.file_uploader("📂 Carregar Relatório de Passagem (PDF)", type=["pdf"])

if uploaded_file:
    df = extrair_dados_sentry(uploaded_file)
    
    if not df.empty:
        df = df.sort_values('data')
        
        # Mapa com Satélite Google
        m = folium.Map(
            location=[df['lat'].iloc[-1], df['lon'].iloc[-1]], 
            zoom_start=13,
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google Satellite"
        )

        # 1. Calor (Histórico de Passagens)
        HeatMap(data=df[['lat', 'lon']], radius=15).add_to(m)

        # 2. Trajeto Recente (Linha de deslocamento)
        folium.PolyLine(df[['lat', 'lon']].values.tolist(), color="#00f2ff", weight=5, opacity=0.7).add_to(m)

        # 3. PONTO DA ABORDAGEM (Seu GPS atual)
        if loc:
            folium.Marker(
                [loc['lat'], loc['lon']],
                popup="LOCAL DA ABORDAGEM ATUAL",
                icon=folium.Icon(color="red", icon="bolt", prefix='fa')
            ).add_to(m)
            st.sidebar.success("📍 Localização da Abordagem Fixada")

        st_folium(m, width="100%", height=600)
    else:
        st.warning("Coordenadas não encontradas no arquivo.")
