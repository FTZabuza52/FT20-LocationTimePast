import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap
import pdfplumber
import re

st.set_page_config(page_title="Radar Sentry Mobile", layout="wide")
st.title("🛡️ Analisador de Campo - Sentry MT")

# Função para extrair dados do PDF do Sentry
def extrair_dados_sentry(pdf_file):
    dados = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            # Busca por Data e Coordenadas no texto do relatório
            datas = re.findall(r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})', text)
            coords = re.findall(r'(-\d+\.\d+) & (-\d+\.\d+)', text)
            
            for i in range(len(coords)):
                dados.append({
                    'data': pd.to_datetime(datas[i], dayfirst=True),
                    'lat': float(coords[i][0]),
                    'lon': float(coords[i][1])
                })
    return pd.DataFrame(dados)

uploaded_file = st.file_uploader("Arraste o PDF do Sentry aqui", type=["pdf"])

if uploaded_file:
    with st.spinner('Processando trajetórias...'):
        df = extrair_dados_sentry(uploaded_file)
        
        if not df.empty:
            # Ordenar por tempo
            df = df.sort_values('data')
            
            # Definir o que é "Recente" (ex: últimas 48h do relatório)
            ultima_passagem = df['data'].max()
            limite = ultima_passagem - pd.Timedelta(hours=48)
            
            historico = df[df['data'] < limite]
            recente = df[df['data'] >= limite]

            # Criar Mapa com fundo Satélite
            m = folium.Map(
                location=[df['lat'].iloc[-1], df['lon'].iloc[-1]], 
                zoom_start=13,
                tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
                attr="Google Satellite"
            )

            # 1. Mapa de Calor (Rotina do Veículo)
            if not historico.empty:
                HeatMap(data=historico[['lat', 'lon']], radius=15, name="Rotina").add_to(m)

            # 2. Rota Recente (Linha de Trajetória)
            if not recente.empty:
                folium.PolyLine(recente[['lat', 'lon']].values.tolist(), color="cyan", weight=4).add_to(m)
                # Marcador da última posição (Abordagem)
                folium.Marker(
                    [recente['lat'].iloc[-1], recente['lon'].iloc[-1]],
                    icon=folium.Icon(color="red", icon="screenshot", prefix='fa')
                ).add_to(m)

            st_folium(m, width="100%", height=500)
            st.write(f"**Veículo:** {uploaded_file.name}")
            st.write(f"**Última passagem detectada:** {ultima_passagem}")
        else:
            st.error("Não foi possível extrair coordenadas deste PDF.")
