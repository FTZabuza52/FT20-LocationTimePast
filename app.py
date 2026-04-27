import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from folium.plugins import HeatMap, Fullscreen
import pdfplumber
import re
from streamlit_js_eval import streamlit_js_eval

# --- CONFIGURAÇÃO DA PÁGINA ---
# Definido no topo para evitar erros de inicialização do Streamlit
st.set_page_config(page_title="FT20 - LTP", layout="wide", page_icon="🦅")

# --- SISTEMA DE LOGIN ---
def check_password():
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    
    if not st.session_state["authenticated"]:
        st.title("Acesso Restrito")
        senha = st.text_input("Digite a senha de acesso:", type="password")
        if st.button("Entrar"):
            if senha == "ft20":  
                st.session_state["authenticated"] = True
                st.rerun()
            else:
                st.error("Senha incorreta")
        return False
    return True

if not check_password():
    st.stop()

# --- HEADER TÁTICO ---
st.markdown("""
    <div style="text-align: center;">
        <h1 style="color: #d32f2f;">FT20 - LTP 🦉🦅⚡📈</h1>
        <p style="font-size: 1.1em; font-weight: bold;">Location Time Past</p>
        <p style="color: #555;">Inteligência e Patrulhamento Tático</p>
    </div>
    <hr style="border: 1px solid #d32f2f;">
""", unsafe_allow_html=True)

# Captura de Localização (GPS do Dispositivo)
loc = streamlit_js_eval(
    js_expressions="new Promise((resolve, reject) => { navigator.geolocation.getCurrentPosition(pos => { resolve({lat: pos.coords.latitude, lon: pos.coords.longitude}) }, err => { reject(err) }) })", 
    key="get_location"
)

# --- PROCESSAMENTO DE DADOS (COM CACHE) ---
@st.cache_data
def extrair_dados_sentry(pdf_file):
    dados = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text: 
                continue
            
            # Padrões específicos do relatório Sentry
            datas = re.findall(r'(\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2})', text)
            coords = re.findall(r'(-\d+\.\d+)\s*&\s*(-\d+\.\d+)', text)
            
            for i in range(min(len(coords), len(datas))):
                dados.append({
                    'data': pd.to_datetime(datas[i], dayfirst=True),
                    'lat': float(coords[i][0]),
                    'lon': float(coords[i][1])
                })
    return pd.DataFrame(dados)

# --- INTERFACE PRINCIPAL ---
uploaded_file = st.file_uploader("📂 Carregar Relatório de Passagem (PDF)", type=["pdf"])

if uploaded_file:
    df = extrair_dados_sentry(uploaded_file)
    
    if not df.empty:
        df = df.sort_values('data')
        
        # Agrupamento para contar registros por coordenada exata
        df_counts = df.groupby(['lat', 'lon']).size().reset_index(name='contagem')

        # Inicialização do Mapa (Centrado no último registro)
        m = folium.Map(
            location=[df['lat'].iloc[-1], df['lon'].iloc[-1]], 
            zoom_start=13,
            tiles="https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}",
            attr="Google Satellite"
        )
        
        # 1. Camada de Mapa de Calor (Densidade Visual)
        HeatMap(data=df[['lat', 'lon']], radius=15, blur=10).add_to(m)
        
        # 2. Camada de Linha (Histórico do Trajeto)
        folium.PolyLine(
            df[['lat', 'lon']].values.tolist(), 
            color="#00f2ff", 
            weight=4, 
            opacity=0.6,
            tooltip="Trajetória registrada"
        ).add_to(m)

        # 3. Camada Interativa (Clique para ver contagem)
        # Criamos círculos quase invisíveis sobre o calor para permitir o clique
        for _, row in df_counts.iterrows():
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=8,
                color='white',
                weight=0.5,
                fill=True,
                fill_color='cyan',
                fill_opacity=0.1, # Mantém o foco visual no mapa de calor
                popup=folium.Popup(f"""
                    <div style='font-family: sans-serif; font-size: 12px;'>
                        <b>Registros:</b> {row['contagem']}<br>
                        <b>Lat:</b> {row['lat']:.5f}<br>
                        <b>Lon:</b> {row['lon']:.5f}
                    </div>
                """, max_width=200),
                tooltip=f"{row['contagem']} passagens detectadas"
            ).add_to(m)

        # 4. Marcador da Localização Atual (GPS)
        if loc:
            folium.Marker(
                [loc['lat'], loc['lon']],
                popup="<b>VOCÊ ESTÁ AQUI</b><br>Ponto de Abordagem Atual",
                icon=folium.Icon(color="red", icon="bolt", prefix='fa')
            ).add_to(m)

        # Ferramentas adicionais do mapa
        Fullscreen().add_to(m)
        
        # Renderização do Mapa
        st_folium(m, width="100%", height=700, returned_objects=[])
        
        # Tabela de resumo opcional abaixo do mapa
        with st.expander("📊 Ver resumo de pontos de interesse"):
            st.dataframe(df_counts.sort_values(by='contagem', ascending=False), use_container_width=True)
            
    else:
        st.warning("Coordenadas não encontradas no arquivo PDF carregado.")
