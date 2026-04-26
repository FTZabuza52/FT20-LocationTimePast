import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap
import pdfplumber
import re
from streamlit_js_eval import streamlit_js_eval

# --- SISTEMA DE LOGIN SIMPLES ---
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    
    if not st.session_state["authenticated"]:
        st.title("Acesso Restrito")
        senha = st.text_input("Digite a senha de acesso:", type="password")
        if st.button("Entrar"):
            if senha == ft20:  # <-- MUDE SUA SENHA AQUI
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Senha incorreta")
        return False
    return True

if not check_password():
    st.stop()

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="FT20 - LTP", layout="wide")
st.title("FT20 - LTP 🦉🦅📈")

# Capturar Localização Atual do Celular
st.sidebar.markdown("### 📍 Localização da Abordagem")
loc = streamlit_js_eval(js_expressions="new Promise((resolve, reject) => { navigator.geolocation.getCurrentPosition(pos => { resolve({lat: pos.coords.latitude, lon: pos.coords.longitude}) }, err => { reject(err) }) })", key="get_location")

if loc:
    st.sidebar.success(f"Localização Capturada: {round(loc['lat'], 4)}, {round(loc['lon'], 4)}")

# --- FUNÇÃO DE EXTRAÇÃO ---
def extrair_dados_sentry(pdf_file):
    dados = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: continue
            datas = re.findall(r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})', text)
            coords = re.findall(r'(-\d+\.\d+)\s*&\s*(-\d+\.\d+)', text)
            for i in range(min(len(coords), len(datas))):
                dados.append({
                    'data': pd.to_datetime(datas[i], dayfirst=True),
                    'lat': float(coords[i][0]),
                    'lon': float(coords[i][1])
                })
    return pd.DataFrame(dados)

uploaded_file = st.file_uploader("Subir PDF do Sentry", type=["pdf"])

if uploaded_file:
    df = extrair_dados_sentry(uploaded_file)
    
    if not df.empty:
        df = df.sort_values('data')
        ultima_p = df['data'].max()
        
        # Mapa com Satélite Google
        m = folium.Map(
            location=[df['lat'].iloc[-1], df['lon'].iloc[-1]], 
            zoom_start=13,
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google Satellite"
        )

        # 1. Calor (Histórico)
        HeatMap(data=df[['lat', 'lon']], radius=15, name="Histórico").add_to(m)

        # 2. Trajeto Recente (Últimas 48h)
        limite = ultima_p - pd.Timedelta(hours=48)
        recente = df[df['data'] >= limite]
        folium.PolyLine(recente[['lat', 'lon']].values.tolist(), color="cyan", weight=5).add_to(m)

        # 3. PONTO DA ABORDAGEM ATUAL (GPS do Celular)
        if loc:
            folium.Marker(
                [loc['lat'], loc['lon']],
                popup="LOCAL DA ABORDAGEM",
                icon=folium.Icon(color="green", icon="bullseye", prefix='fa')
            ).add_to(m)

        st_folium(m, width="100%", height=600)
        st.write(f"Última Passagem no PDF: {ultima_p}")
    else:
        st.warning("Nenhuma coordenada encontrada no PDF.")
