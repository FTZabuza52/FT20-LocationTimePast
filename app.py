import gc
import io
import re
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
import plotly.express as px
import pydeck as pdk
import streamlit as st

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    from pypdf import PdfReader
except ImportError:
    try:
        from PyPDF2 import PdfReader
    except ImportError:
        PdfReader = None

# ==============================================================================
# CONFIGURAÇÃO DA PÁGINA & AUTENTICAÇÃO BLINDADA
# ==============================================================================
st.set_page_config(
    page_title="SENTRY INTEL MT — Análise Operacional",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def verificar_senha() -> bool:
    """Protege o acesso ao painel sem quebrar caso Secrets não esteja configurado."""
    if st.session_state.get("autenticado", False):
        return True

    st.markdown("## 🛡️ SENTRY INTEL MT — Acesso Restrito")
    st.caption("Sistema de Inteligência de Rotas, Cinemática Veicular e Análise Estatística.")

    try:
        senha_configurada = st.secrets.get("APP_PASSWORD", None)
    except Exception:
        senha_configurada = None

    if not senha_configurada:
        st.info("ℹ️ Usando senha padrão operacional (`pmmt2026`).")

    with st.form("form_login"):
        senha_digitada = st.text_input("Senha Operacional", type="password")
        entrar = st.form_submit_button("Acessar Sistema", use_container_width=True)

        if entrar:
            alvo = senha_configurada if senha_configurada else "pmmt2026"
            if senha_digitada == alvo:
                st.session_state["autenticado"] = True
                st.rerun()
            else:
                st.error("❌ Senha incorreta.")
    return False


if not verificar_senha():
    st.stop()

# ==============================================================================
# TOPOLOGIA VIÁRIA CALIBRADA DE MATO GROSSO (EIXO RO/BOLÍVIA + EIXO MS -> BG)
# ==============================================================================
PONTOS_POR_ID = {
    # Fronteira Oeste / Vila Bela / Bolívia
    "13":   {"nome": "Ponte Vila Bela (Sent. Bolívia)", "zona": "01_VILA_BELA_FRONTEIRA", "regiao": "Fronteira Bolívia (Vila Bela)", "dist_bg": 1020, "lat": -15.0068, "lon": -59.9547, "sentido_bg": "AFASTAMENTO", "h_min_bg": 12.0, "h_max_bg": 16.0},
    "14":   {"nome": "Ponte Vila Bela (Ent. P. Lacerda)", "zona": "01_VILA_BELA_FRONTEIRA", "regiao": "Fronteira Bolívia (Vila Bela)", "dist_bg": 1020, "lat": -15.0068, "lon": -59.9547, "sentido_bg": "APROXIMACAO", "h_min_bg": 12.0, "h_max_bg": 16.0},
    "185":  {"nome": "Vila Bela MT-199 Km 01 (Saída PL)", "zona": "01_VILA_BELA_FRONTEIRA", "regiao": "Fronteira Bolívia (Vila Bela)", "dist_bg": 1017, "lat": -15.0150, "lon": -59.9400, "sentido_bg": "APROXIMACAO", "h_min_bg": 12.0, "h_max_bg": 16.0},
    "186":  {"nome": "Vila Bela MT-199 Km 01 (Bidir.)", "zona": "01_VILA_BELA_FRONTEIRA", "regiao": "Fronteira Bolívia (Vila Bela)", "dist_bg": 1017, "lat": -15.0150, "lon": -59.9400, "sentido_bg": "BIDIR", "h_min_bg": 12.0, "h_max_bg": 16.0},
    "1436": {"nome": "Vila Bela Urbano (Verena Leite)", "zona": "90_URBANO_INTERNO", "regiao": "Fronteira Bolívia (Vila Bela)", "dist_bg": 1018, "lat": -15.0080, "lon": -59.9510, "sentido_bg": "INTERNO", "h_min_bg": 12.0, "h_max_bg": 16.0},
    "181":  {"nome": "BR-174 Km 78 Arrozal (Sent. PL)", "zona": "02_ARROZAL_KM78", "regiao": "Fronteira Bolívia (Vila Bela)", "dist_bg": 978, "lat": -15.1820, "lon": -59.6850, "sentido_bg": "APROXIMACAO", "h_min_bg": 11.5, "h_max_bg": 15.5},
    "184":  {"nome": "BR-174 Km 78 Arrozal (Sent. Bolívia)", "zona": "02_ARROZAL_KM78", "regiao": "Fronteira Bolívia (Vila Bela)", "dist_bg": 978, "lat": -15.1820, "lon": -59.6850, "sentido_bg": "AFASTAMENTO", "h_min_bg": 11.5, "h_max_bg": 15.5},
    "183":  {"nome": "BR-174 Km 25 Serra da Borda (Ent. PL)", "zona": "03_SERRA_BORDA_KM25", "regiao": "Fronteira Bolívia (Vila Bela)", "dist_bg": 940, "lat": -15.2150, "lon": -59.4200, "sentido_bg": "APROXIMACAO", "h_min_bg": 11.0, "h_max_bg": 14.5},
    "182":  {"nome": "BR-174 Km 25 Serra da Borda (Saída VB)", "zona": "03_SERRA_BORDA_KM25", "regiao": "Fronteira Bolívia (Vila Bela)", "dist_bg": 940, "lat": -15.2150, "lon": -59.4200, "sentido_bg": "AFASTAMENTO", "h_min_bg": 11.0, "h_max_bg": 14.5},
    # Descida RO -> Pontes e Lacerda
    "180":  {"nome": "BR-174 Km 310 Fazendinha (Ent. PL)", "zona": "02B_CONQUISTA_DOESTE", "regiao": "Divisa com Rondônia (Conquista D'Oeste)", "dist_bg": 965, "lat": -14.8550, "lon": -59.5450, "sentido_bg": "APROXIMACAO", "h_min_bg": 11.2, "h_max_bg": 15.0},
    "179":  {"nome": "BR-174 Km 310 Fazendinha (Saída RO)", "zona": "02B_CONQUISTA_DOESTE", "regiao": "Divisa com Rondônia (Conquista D'Oeste)", "dist_bg": 965, "lat": -14.8550, "lon": -59.5450, "sentido_bg": "AFASTAMENTO", "h_min_bg": 11.2, "h_max_bg": 15.0},
    # Pontes e Lacerda
    "296":  {"nome": "P. Lacerda MT-473 Km 3 (Bolívia -> PL)", "zona": "03B_PL_MT473_FRONTEIRA", "regiao": "Fronteira Bolívia (Pontes e Lacerda)", "dist_bg": 925, "lat": -15.2520, "lon": -59.3550, "sentido_bg": "APROXIMACAO", "h_min_bg": 10.8, "h_max_bg": 14.5},
    "295":  {"nome": "P. Lacerda MT-473 Km 3 (PL -> Bolívia)", "zona": "03B_PL_MT473_FRONTEIRA", "regiao": "Fronteira Bolívia (Pontes e Lacerda)", "dist_bg": 925, "lat": -15.2520, "lon": -59.3550, "sentido_bg": "AFASTAMENTO", "h_min_bg": 10.8, "h_max_bg": 14.5},
    "2066": {"nome": "Pontes e Lacerda BR-174 Norte", "zona": "04_PONTES_LACERDA", "regiao": "Pontes e Lacerda", "dist_bg": 930, "lat": -15.2180, "lon": -59.3320, "sentido_bg": "BIDIR", "h_min_bg": 10.5, "h_max_bg": 14.0},
    "178":  {"nome": "BR-174 Km 277 CDP (PL <-> Cáceres)", "zona": "04_PONTES_LACERDA", "regiao": "Pontes e Lacerda", "dist_bg": 915, "lat": -15.2950, "lon": -59.2850, "sentido_bg": "BIDIR", "h_min_bg": 10.3, "h_max_bg": 13.8},
    "177":  {"nome": "BR-174 Km 277 CDP (PL <-> Bolívia)", "zona": "04_PONTES_LACERDA", "regiao": "Pontes e Lacerda", "dist_bg": 915, "lat": -15.2950, "lon": -59.2850, "sentido_bg": "BIDIR", "h_min_bg": 10.3, "h_max_bg": 13.8},
    "367":  {"nome": "BR-174 Km 286 P. Lacerda (Ent.)", "zona": "04_PONTES_LACERDA", "regiao": "Pontes e Lacerda", "dist_bg": 925, "lat": -15.2350, "lon": -59.3200, "sentido_bg": "AFASTAMENTO", "h_min_bg": 10.5, "h_max_bg": 14.0},
    # Bom Futuro -> Porto Esperidião -> Cáceres
    "1822": {"nome": "Bom Futuro Faz. Felicidade (Sent. P. Esp.)", "zona": "05_BOM_FUTURO_KM155", "regiao": "Porto Esperidião", "dist_bg": 840, "lat": -15.5850, "lon": -58.9650, "sentido_bg": "APROXIMACAO", "h_min_bg": 9.8, "h_max_bg": 13.0},
    "1821": {"nome": "Bom Futuro Faz. Felicidade (Sent. PL)", "zona": "05_BOM_FUTURO_KM155", "regiao": "Porto Esperidião", "dist_bg": 840, "lat": -15.5850, "lon": -58.9650, "sentido_bg": "AFASTAMENTO", "h_min_bg": 9.8, "h_max_bg": 13.0},
    "25":   {"nome": "BR-174 Km 176 P. Esperidião (Ent. PL)", "zona": "06_PORTO_ESPERIDIAO", "regiao": "Porto Esperidião", "dist_bg": 822, "lat": -15.8450, "lon": -58.4750, "sentido_bg": "APROXIMACAO", "h_min_bg": 9.2, "h_max_bg": 12.2},
    "26":   {"nome": "BR-174 Km 176 P. Esperidião (Saída PL)", "zona": "06_PORTO_ESPERIDIAO", "regiao": "Porto Esperidião", "dist_bg": 822, "lat": -15.8450, "lon": -58.4750, "sentido_bg": "AFASTAMENTO", "h_min_bg": 9.2, "h_max_bg": 12.2},
    "32":   {"nome": "BR-174 Km 166 P. Esperidião (Saída Cáceres)", "zona": "06_PORTO_ESPERIDIAO", "regiao": "Porto Esperidião", "dist_bg": 812, "lat": -15.8620, "lon": -58.4520, "sentido_bg": "APROXIMACAO", "h_min_bg": 9.0, "h_max_bg": 12.0},
    "31":   {"nome": "BR-174 Km 166 P. Esperidião (Ent. Cáceres)", "zona": "06_PORTO_ESPERIDIAO", "regiao": "Porto Esperidião", "dist_bg": 812, "lat": -15.8620, "lon": -58.4520, "sentido_bg": "AFASTAMENTO", "h_min_bg": 9.0, "h_max_bg": 12.0},
    "23":   {"nome": "MT-265 Km 01 P. Esperidião -> Bolívia", "zona": "06B_PORTO_ESPERIDIAO_BOL", "regiao": "Fronteira Bolívia (Porto Esperidião)", "dist_bg": 818, "lat": -15.8750, "lon": -58.4900, "sentido_bg": "AFASTAMENTO", "h_min_bg": 9.2, "h_max_bg": 12.2},
    "24":   {"nome": "MT-265 Km 01 Bolívia -> P. Esperidião", "zona": "06B_PORTO_ESPERIDIAO_BOL", "regiao": "Fronteira Bolívia (Porto Esperidião)", "dist_bg": 818, "lat": -15.8750, "lon": -58.4900, "sentido_bg": "APROXIMACAO", "h_min_bg": 9.2, "h_max_bg": 12.2},
    "376":  {"nome": "BR-070 Km 743 Cáceres (Ent. Oeste)", "zona": "07_CACERES_BR070", "regiao": "Cáceres", "dist_bg": 705, "lat": -16.0780, "lon": -57.6450, "sentido_bg": "APROXIMACAO", "h_min_bg": 7.8, "h_max_bg": 10.5},
    "377":  {"nome": "BR-070 Km 736 Cáceres (Saída Oeste)", "zona": "07_CACERES_BR070", "regiao": "Cáceres", "dist_bg": 705, "lat": -16.0710, "lon": -57.6580, "sentido_bg": "AFASTAMENTO", "h_min_bg": 7.8, "h_max_bg": 10.5},
    # Funil Leste (Campo Verde / Primavera)
    "572":  {"nome": "Campo Verde Saída Primavera (Sent. CV)", "zona": "09_CAMPO_VERDE_FUNIL", "regiao": "Campo Verde", "dist_bg": 370, "lat": -15.5450, "lon": -55.1620, "sentido_bg": "AFASTAMENTO", "h_min_bg": 4.2, "h_max_bg": 6.0},
    "369":  {"nome": "BR-070 Km 283 Primavera do Leste (Ent. CV)", "zona": "10_PRIMAVERA_FUNIL", "regiao": "Primavera do Leste", "dist_bg": 275, "lat": -15.5781, "lon": -54.3920, "sentido_bg": "APROXIMACAO", "h_min_bg": 3.2, "h_max_bg": 4.8},
    # Eixo Sul / Divisa MS -> Itiquira -> Rondonópolis -> Alto Garças / Alto Taquari
    "36":   {"nome": "PP01 Itiquira BR-163 Km 34 (MS -> Rondonópolis)", "zona": "15_DIVISA_MS_ITIQUIRA", "regiao": "Divisa com MS (Itiquira / Sonora)", "dist_bg": 640, "lat": -17.2194, "lon": -54.7586, "sentido_bg": "APROXIMACAO", "h_min_bg": 6.8, "h_max_bg": 9.2},
    "38":   {"nome": "PP01 Itiquira BR-163 Km 34 (MS -> Rondonópolis)", "zona": "15_DIVISA_MS_ITIQUIRA", "regiao": "Divisa com MS (Itiquira / Sonora)", "dist_bg": 640, "lat": -17.2194, "lon": -54.7586, "sentido_bg": "APROXIMACAO", "h_min_bg": 6.8, "h_max_bg": 9.2},
    "39":   {"nome": "PP01 Itiquira BR-163 Km 34 (MS -> Rondonópolis)", "zona": "15_DIVISA_MS_ITIQUIRA", "regiao": "Divisa com MS (Itiquira / Sonora)", "dist_bg": 640, "lat": -17.2194, "lon": -54.7586, "sentido_bg": "APROXIMACAO", "h_min_bg": 6.8, "h_max_bg": 9.2},
    "41":   {"nome": "PP01 Itiquira BR-163 Km 34 (Rondonópolis -> MS)", "zona": "15_DIVISA_MS_ITIQUIRA", "regiao": "Divisa com MS (Itiquira / Sonora)", "dist_bg": 640, "lat": -17.2194, "lon": -54.7586, "sentido_bg": "AFASTAMENTO", "h_min_bg": 6.8, "h_max_bg": 9.2},
    "43":   {"nome": "PP01 Itiquira BR-163 Km 34 (Rondonópolis -> MS)", "zona": "15_DIVISA_MS_ITIQUIRA", "regiao": "Divisa com MS (Itiquira / Sonora)", "dist_bg": 640, "lat": -17.2194, "lon": -54.7586, "sentido_bg": "AFASTAMENTO", "h_min_bg": 6.8, "h_max_bg": 9.2},
    "384":  {"nome": "BR-163 Km 44 Itiquira (MS -> Rondonópolis)", "zona": "15_DIVISA_MS_ITIQUIRA", "regiao": "Divisa com MS (Itiquira / Sonora)", "dist_bg": 625, "lat": -17.1194, "lon": -54.7597, "sentido_bg": "APROXIMACAO", "h_min_bg": 6.6, "h_max_bg": 9.0},
    "385":  {"nome": "BR-163 Km 44 Itiquira (MS -> Rondonópolis)", "zona": "15_DIVISA_MS_ITIQUIRA", "regiao": "Divisa com MS (Itiquira / Sonora)", "dist_bg": 625, "lat": -17.1194, "lon": -54.7597, "sentido_bg": "APROXIMACAO", "h_min_bg": 6.6, "h_max_bg": 9.0},
    "1627": {"nome": "Alto Taquari MT-100 (Divisa MS -> Norte/BG)", "zona": "18_ALTO_GARCAS_TAQUARI", "regiao": "Divisa com MS (Alto Taquari / MT-100)", "dist_bg": 330, "lat": -17.8260, "lon": -53.2850, "sentido_bg": "APROXIMACAO", "h_min_bg": 3.5, "h_max_bg": 5.0},
    "294":  {"nome": "Alto Garças BR-364 (Pedra Preta -> Alto Garças)", "zona": "18_ALTO_GARCAS_TAQUARI", "regiao": "Alto Garças (Rota Sul)", "dist_bg": 340, "lat": -16.9440, "lon": -53.5280, "sentido_bg": "APROXIMACAO", "h_min_bg": 3.6, "h_max_bg": 5.2},
    "382":  {"nome": "BR-364 Km 55 Alto Garças (Sent. Alto Araguaia)", "zona": "18_ALTO_GARCAS_TAQUARI", "regiao": "Alto Garças (Rota Sul)", "dist_bg": 335, "lat": -16.9500, "lon": -53.5100, "sentido_bg": "APROXIMACAO", "h_min_bg": 3.5, "h_max_bg": 5.0},
}


def classificar_local_dinamico(cam_id: str, local_texto: str) -> dict:
    """Resolve metadados geográficos, região operacional e aproximação rumo a Barra do Garças."""
    if cam_id in PONTOS_POR_ID:
        return PONTOS_POR_ID[cam_id]

    u = local_texto.upper()
    is_interno = "(INTERNO)" in u and "BR-70" not in u and "BR 070" not in u and "BR-364" not in u and "BR-163" not in u

    sentido_bg = "APROXIMACAO"
    if any(k in u for k in [
        "-> CÁCERES (SAÍDA)", "-> PONTES E LACERDA (SAÍDA)", "-> BOLÍVIA", "-> BOLIVIA",
        "-> CONQUISTA", "-> VILA BELA", "-> CAMPO VERDE", "-> CUIABÁ", "-> DIAMANTINO",
        "-> SONORA/MS", "SENTIDO SONORA", "SENTIDO RONDONÓPOLIS"
    ]):
        sentido_bg = "AFASTAMENTO"
    elif "BIDIRECIONAL" in u:
        sentido_bg = "BIDIR"
    elif is_interno:
        sentido_bg = "INTERNO"

    regras_geo = [
        ("CONQUISTA D'OESTE", "02B_CONQUISTA_DOESTE", "Divisa com Rondônia (Conquista D'Oeste)", 965, -14.8400, -59.5500, 11.2, 15.0),
        ("VILHENA", "02B_CONQUISTA_DOESTE", "Divisa com Rondônia (Vilhena)", 1050, -12.8894, -60.0569, 12.0, 16.0),
        ("CAMPOS DE JÚLIO", "08A_ARCO_NORTE_CHAPADAO", "Arco Norte (Campos de Júlio)", 800, -13.8950, -59.1450, 9.5, 13.5),
        ("SAPEZAL", "08A_ARCO_NORTE_CHAPADAO", "Arco Norte (Sapezal)", 780, -13.5406, -58.7229, 9.2, 13.0),
        ("CAMPO NOVO DO PARECIS", "08A_ARCO_NORTE_CHAPADAO", "Arco Norte (Campo Novo do Parecis)", 710, -13.6750, -57.8900, 8.5, 12.0),
        ("DIAMANTINO", "08B_ARCO_NORTE_NOBRES", "Arco Norte (Diamantino)", 540, -14.4080, -56.4460, 6.8, 9.5),
        ("NOBRES", "08B_ARCO_NORTE_NOBRES", "Arco Norte (Nobres)", 510, -14.7200, -56.3270, 6.5, 9.0),
        ("ROSARIO OESTE", "08B_ARCO_NORTE_NOBRES", "Arco Norte (Rosário Oeste)", 490, -14.8360, -56.4270, 6.3, 8.8),
        ("LEVERGER", "08C_SERRA_SAO_VICENTE", "Serra de São Vicente", 440, -15.8200, -55.4200, 5.0, 7.0),
        ("PP04", "08C_SERRA_SAO_VICENTE", "Serra de São Vicente", 440, -15.8200, -55.4200, 5.0, 7.0),
        ("JACIARA", "17_JACIARA_BR364", "Jaciara (BR-364)", 415, -15.9525, -54.9947, 4.6, 6.5),
        ("CAMPO VERDE", "09_CAMPO_VERDE_FUNIL", "Campo Verde", 370, -15.5450, -55.1620, 4.2, 6.0),
        ("PP03", "09_CAMPO_VERDE_FUNIL", "Campo Verde", 370, -15.5450, -55.1620, 4.2, 6.0),
        ("PRIMAVERA DO LESTE", "10_PRIMAVERA_FUNIL", "Primavera do Leste", 275, -15.5580, -54.2950, 3.2, 4.8),
        ("ITIQUIRA", "15_DIVISA_MS_ITIQUIRA", "Divisa com MS (Itiquira / Sonora)", 630, -17.2194, -54.7586, 6.6, 9.0),
        ("PP01", "15_DIVISA_MS_ITIQUIRA", "Divisa com MS (Itiquira / Sonora)", 630, -17.2194, -54.7586, 6.6, 9.0),
        ("RONDONOPOLIS", "16_RONDONOPOLIS_EIXO", "Rondonópolis", 490, -16.4455, -54.6695, 5.2, 7.2),
        ("RONDONÓPOLIS", "16_RONDONOPOLIS_EIXO", "Rondonópolis", 490, -16.4455, -54.6695, 5.2, 7.2),
        ("PEDRA PRETA", "18_ALTO_GARCAS_TAQUARI", "Pedra Preta (Rota Sul)", 455, -16.6230, -54.4740, 4.8, 6.8),
        ("ALTO GARCAS", "18_ALTO_GARCAS_TAQUARI", "Alto Garças (Rota Sul)", 340, -16.9440, -53.5280, 3.6, 5.2),
        ("ALTO GARÇAS", "18_ALTO_GARCAS_TAQUARI", "Alto Garças (Rota Sul)", 340, -16.9440, -53.5280, 3.6, 5.2),
        ("ALTO TAQUARI", "18_ALTO_GARCAS_TAQUARI", "Divisa com MS (Alto Taquari / MT-100)", 330, -17.8260, -53.2850, 3.5, 5.0),
        ("ALTO ARAGUAIA", "18_ALTO_GARCAS_TAQUARI", "Alto Araguaia (Divisa GO/MS)", 280, -17.3140, -53.2150, 3.0, 4.5),
        ("TESOURO", "11A_DESVIO_SUL_TESOURO", "Desvio Sul (Tesouro)", 210, -16.0780, -53.5560, 2.5, 3.8),
        ("GUIRATINGA", "11B_DESVIO_SUL_GUIRATINGA", "Desvio Sul (Guiratinga)", 180, -16.3480, -53.7580, 2.0, 3.3),
        ("GENERAL CARNEIRO", "11C_RETA_BR070_GEN_CARNEIRO", "General Carneiro (Reta BG)", 80, -15.7100, -52.7550, 0.8, 1.3),
        ("TORIXOR", "12_CHEGADA_MT100_BG", "Torixoréu (MT-100)", 50, -16.1980, -52.5560, 0.5, 0.9),
        ("PONTAL DO ARAGUAIA", "13_DIVISA_BARRA_DO_GARCAS", "Barra do Garças / Pontal", 5, -15.9050, -52.2650, 0.0, 0.2),
        ("BARRA DO GAR", "13_DIVISA_BARRA_DO_GARCAS", "Barra do Garças", 0, -15.8900, -52.2560, 0.0, 0.0),
        ("CUIAB", "08D_CUIABA_VG", "Cuiabá / Várzea Grande", 515, -15.6010, -56.0970, 5.5, 7.5),
        ("CBA", "08D_CUIABA_VG", "Cuiabá / Várzea Grande", 515, -15.6010, -56.0970, 5.5, 7.5),
        ("BEIRA RIO", "08D_CUIABA_VG", "Cuiabá / Várzea Grande", 515, -15.6188, -56.0986, 5.5, 7.5),
        ("FERNANDO CORREA", "08D_CUIABA_VG", "Cuiabá / Várzea Grande", 515, -15.6258, -56.0596, 5.5, 7.5),
        ("MIGUEL SUTIL", "08D_CUIABA_VG", "Cuiabá / Várzea Grande", 515, -15.6051, -56.0781, 5.5, 7.5),
        ("PONTE NOVA", "08D_CUIABA_VG", "Cuiabá / Várzea Grande", 518, -15.6232, -56.1175, 5.5, 7.5),
        ("PONTE VELHA", "08D_CUIABA_VG", "Cuiabá / Várzea Grande", 518, -15.6151, -56.1052, 5.5, 7.5),
        ("SERGIO MOTTA", "08D_CUIABA_VG", "Cuiabá / Várzea Grande", 516, -15.6314, -56.0816, 5.5, 7.5),
        ("VARZEA GRANDE", "08D_CUIABA_VG", "Cuiabá / Várzea Grande", 520, -15.6460, -56.1320, 5.6, 7.6),
        ("VÁRZEA GRANDE", "08D_CUIABA_VG", "Cuiabá / Várzea Grande", 520, -15.6460, -56.1320, 5.6, 7.6),
        ("POCON", "07C_POCONE_BR070", "Poconé (BR-070)", 610, -16.2560, -56.6220, 6.6, 8.8),
        ("MIRASSOL", "07B_MT175_INTERIOR", "Região Oeste (Mirassol D'Oeste)", 740, -15.6750, -58.0950, 8.2, 11.0),
        ("QUATRO MARCOS", "07B_MT175_INTERIOR", "Região Oeste (Quatro Marcos)", 760, -15.6200, -58.1750, 8.5, 11.3),
        ("ARAPUTANGA", "07B_MT175_INTERIOR", "Região Oeste (Araputanga)", 780, -15.4650, -58.3450, 8.8, 11.6),
        ("ALTA FLORESTA", "20_NORTE_MT_ALTA_FLORESTA", "Norte MT (Alta Floresta)", 1150, -9.8756, -56.0861, 13.5, 17.5),
    ]

    for kw, zona, regiao, dist_bg, lat, lon, hmin, hmax in regras_geo:
        if kw in u:
            return {
                "nome": local_texto[:55],
                "zona": "90_URBANO_INTERNO" if is_interno else zona,
                "regiao": regiao,
                "dist_bg": dist_bg,
                "lat": lat,
                "lon": lon,
                "sentido_bg": sentido_bg,
                "h_min_bg": hmin,
                "h_max_bg": hmax,
            }

    return {
        "nome": local_texto[:55],
        "zona": "90_URBANO_INTERNO" if is_interno else "99_OUTRO_PONTO",
        "regiao": "Outra Localidade MT",
        "dist_bg": np.nan,
        "lat": np.nan,
        "lon": np.nan,
        "sentido_bg": sentido_bg,
        "h_min_bg": np.nan,
        "h_max_bg": np.nan,
    }


def extrair_cam_id_universal(loc_text: str) -> str:
    m = re.search(r"\bID\s*:?\s*(\d+)\b", loc_text, re.IGNORECASE)
    if m:
        return m.group(1)
    m = re.search(r"\(\s*(\d+)\s*-", loc_text)
    if m:
        return m.group(1)
    matches = re.findall(r"\b(\d{1,5})\s+-\s+(?!KM\b|MT\b|BR\b)([A-ZÁÉÍÓÚÂÊÔÃÕÇ\(])", loc_text)
    if matches:
        return matches[-1][0]
    return "SEM_ID"


def _otimizar_memoria_df(df: pd.DataFrame) -> pd.DataFrame:
    """Compacta colunas repetitivas e float64 para reduzir o consumo de RAM no Streamlit Cloud."""
    if df.empty:
        return df
    cols_cat = ["arquivo", "status_ocr", "cam_id", "monitoramento", "nome", "zona", "regiao", "sentido_bg"]
    for c in cols_cat:
        if c in df.columns:
            df[c] = df[c].astype("category")
    for c in ["dist_bg", "lat", "lon", "h_min_bg", "h_max_bg"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("float32")
    return df


# ==============================================================================
# PARSER UNIVERSAL 7-EM-1 (XLSX, CSV E TODOS OS PADRÕES DE PDF DO SENTRY)
# ==============================================================================
def parse_arquivo_sentry(nome_arquivo: str, raw_bytes: bytes) -> pd.DataFrame:
    valid_plate_re = re.compile(r"^[A-Z]{3}[0-9][A-Z0-9][0-9]{2}$")
    nome_low = nome_arquivo.lower()
    records = []

    def montar_registro(placa_raw, dt_val, loc_full, lat_val=np.nan, lon_val=np.nan, mon="NÃO"):
        if pd.isna(dt_val):
            return
        p_raw = str(placa_raw).strip() if pd.notna(placa_raw) else ""
        if p_raw.lower() in {"nan", "none", "null"}:
            p_raw = ""
        p_clean = re.sub(r"[^A-Z0-9]", "", p_raw.upper())
        if not p_clean:
            status_ocr = "SEM_PLACA_OCR"
        elif valid_plate_re.match(p_clean):
            status_ocr = "VALIDA"
        else:
            status_ocr = "PARCIAL_OCR"

        loc_clean = re.sub(r"\s+", " ", str(loc_full)).strip()
        cam_id = extrair_cam_id_universal(loc_clean)
        meta = classificar_local_dinamico(cam_id, loc_clean)

        lat_final = float(lat_val) if pd.notna(lat_val) else meta["lat"]
        lon_final = float(lon_val) if pd.notna(lon_val) else meta["lon"]

        records.append({
            "arquivo": nome_arquivo,
            "placa": p_clean if p_clean else "SEM_LEITURA",
            "placa_fmt": p_raw if p_raw else "(em branco)",
            "status_ocr": status_ocr,
            "timestamp": dt_val,
            "cam_id": cam_id,
            "local": loc_clean,
            "monitoramento": "SIM" if "SIM" in str(mon).upper() else "NÃO",
            "nome": meta["nome"],
            "zona": meta["zona"],
            "regiao": meta["regiao"],
            "dist_bg": meta["dist_bg"],
            "lat": lat_final,
            "lon": lon_final,
            "sentido_bg": meta["sentido_bg"],
            "h_min_bg": meta["h_min_bg"],
            "h_max_bg": meta["h_max_bg"],
        })

    # 1. PLANILHA EXCEL (.xlsx / .xls)
    if nome_low.endswith((".xlsx", ".xls")):
        xls = pd.ExcelFile(io.BytesIO(raw_bytes))
        if "Sentry" in xls.sheet_names:
            df_s = pd.read_excel(xls, sheet_name="Sentry")
            cols_low = {c.lower().strip(): c for c in df_s.columns}
            if "data/hora" in cols_low:
                c_p = cols_low.get("placa")
                c_dt = cols_low.get("data/hora")
                c_loc = cols_low.get("local/sentido") or cols_low.get("local")
                c_lat = cols_low.get("latitude")
                c_lon = cols_low.get("longitude")
                dts = pd.to_datetime(df_s[c_dt], dayfirst=True, errors="coerce")
                for idx in range(len(df_s)):
                    if pd.isna(dts.iloc[idx]):
                        continue
                    montar_registro(
                        df_s[c_p].iloc[idx] if c_p else "",
                        dts.iloc[idx],
                        df_s[c_loc].iloc[idx] if c_loc else "",
                        pd.to_numeric(df_s[c_lat].iloc[idx], errors="coerce") if c_lat else np.nan,
                        pd.to_numeric(df_s[c_lon].iloc[idx], errors="coerce") if c_lon else np.nan,
                    )
                return _otimizar_memoria_df(pd.DataFrame(records))

        all_lines = []
        for s in xls.sheet_names:
            df_t = pd.read_excel(xls, sheet_name=s, header=None)
            for _, row in df_t.iterrows():
                for val in row:
                    if pd.notna(val):
                        for part in str(val).splitlines():
                            p_str = part.strip()
                            if p_str:
                                all_lines.append(p_str)
        lines = all_lines

    # 2. CSV (.csv)
    elif nome_low.endswith(".csv"):
        texto = raw_bytes.decode("utf-8", errors="replace")
        raw_lines = [l.strip() for l in texto.splitlines() if l.strip()]
        if raw_lines and ("Data/hora" in raw_lines[0] or "Data/Hora" in raw_lines[0]) and ("," in raw_lines[0] or ";" in raw_lines[0]):
            sep = ";" if ";" in raw_lines[0] else ","
            try:
                df_c = pd.read_csv(io.StringIO(texto), sep=sep)
                cols_low = {c.lower().strip(): c for c in df_c.columns}
                c_p = cols_low.get("placa")
                c_dt = cols_low.get("data/hora")
                c_loc = cols_low.get("local/sentido") or cols_low.get("local")
                c_lat = cols_low.get("latitude")
                c_lon = cols_low.get("longitude")
                c_mon = cols_low.get("monitoramento")
                if c_dt:
                    dts = pd.to_datetime(df_c[c_dt], dayfirst=True, errors="coerce")
                    for idx in range(len(df_c)):
                        if pd.isna(dts.iloc[idx]):
                            continue
                        montar_registro(
                            df_c[c_p].iloc[idx] if c_p else "",
                            dts.iloc[idx],
                            df_c[c_loc].iloc[idx] if c_loc else "",
                            pd.to_numeric(df_c[c_lat].iloc[idx], errors="coerce") if c_lat else np.nan,
                            pd.to_numeric(df_c[c_lon].iloc[idx], errors="coerce") if c_lon else np.nan,
                            df_c[c_mon].iloc[idx] if c_mon else "NÃO",
                        )
                    return _otimizar_memoria_df(pd.DataFrame(records))
            except Exception:
                pass
        lines = [l.strip().strip('"').replace("\x0c", "").strip() for l in raw_lines if l.strip().strip('"').replace("\x0c", "").strip()]

    # 3. PDF (.pdf)
    else:
        texto = ""
        if fitz is not None:
            doc = fitz.open(stream=raw_bytes, filetype="pdf")
            texto = "\n".join(page.get_text("text") for page in doc)
            doc.close()
        elif PdfReader is not None:
            reader = PdfReader(io.BytesIO(raw_bytes))
            texto = "\n".join((page.extract_text() or "") for page in reader.pages)
        else:
            raise RuntimeError("Instale PyMuPDF ou pypdf no requirements.txt para ler arquivos PDF.")
        lines = [l.strip() for l in texto.splitlines() if l.strip()]

    if not lines:
        return pd.DataFrame()

    header_blob = " ".join(lines[:25])
    m_hdr_plate = re.search(r"Placa:\s*([A-Z]{3}-?[0-9][A-Z0-9][0-9]{2})", header_blob, re.IGNORECASE)
    placa_cabecalho_fmt = m_hdr_plate.group(1).upper() if m_hdr_plate else ""

    dt_inline_re = re.compile(r"^(?:Data/Hora\s+)?(\d{2}/\d{2}/\d{4}\s+\d{2}:\d{2}:\d{2})$", re.IGNORECASE)
    has_inline_dt = any(dt_inline_re.match(l) for l in lines[:40])

    if has_inline_dt:
        clean_lines = [
            l for l in lines
            if not (
                l.startswith((
                    "SESP -", "CENTRO POLÍTICO", "CENTRO POLITICO", "RELATÓRIO DE PESQUISA",
                    "Data inicial:", "Data Inicial:", "Filtro utilizado:", "Total de passagens:",
                    "Câmeras:", "Impresso em", "Imagem não", "imagem não", "sentry -"
                ))
                or re.match(r"^\d+/\d+$", l)
            )
        ]
        dt_indices = [idx for idx, l in enumerate(clean_lines) if dt_inline_re.match(l)]

        for k, dt_idx in enumerate(dt_indices):
            dt_str = dt_inline_re.match(clean_lines[dt_idx]).group(1)
            dt_val = pd.to_datetime(dt_str, dayfirst=True, errors="coerce")

            placa_raw = placa_cabecalho_fmt
            for back in range(1, 4):
                if dt_idx - back >= 0:
                    prev_l = clean_lines[dt_idx - back]
                    m_p = re.search(r"\b([A-Z]{3}-?[0-9][A-Z0-9][0-9]{2})\b", prev_l.upper())
                    if m_p:
                        placa_raw = m_p.group(1)
                        break

            end_idx = dt_indices[k + 1] if (k + 1 < len(dt_indices)) else len(clean_lines)
            while end_idx - 1 > dt_idx and (
                clean_lines[end_idx - 1].startswith("Placa")
                or re.match(r"^[A-Z]{3}-?[0-9][A-Z0-9][0-9]{2}$", clean_lines[end_idx - 1].strip().upper())
            ):
                end_idx -= 1

            bloco = " ".join(clean_lines[dt_idx + 1 : end_idx])
            lat_v, lon_v = np.nan, np.nan
            m_coord = re.search(r"(-?\d{1,2}\.\d+)\s*[,;\s]\s*(-?\d{1,3}\.\d+)", bloco)
            if m_coord:
                lat_v = float(m_coord.group(1))
                lon_v = float(m_coord.group(2))
                bloco = re.sub(r"Coordenadas\s+do\s+local.*$", "", bloco, flags=re.IGNORECASE).strip()

            loc_clean = re.sub(r"^Local\s*", "", bloco, flags=re.IGNORECASE).replace(" Local ", " ").strip()
            montar_registro(placa_raw, dt_val, loc_clean, lat_v, lon_v, "NÃO")

        return _otimizar_memoria_df(pd.DataFrame(records))

    dt_only_re = re.compile(r"^(\d{2}/\d{2}/\d{4})$")
    tm_only_re = re.compile(r"^(\d{2}:\d{2}:\d{2})$")

    current_date = ""
    i = 0
    while i < len(lines):
        l = lines[i]
        m_d = dt_only_re.match(l)
        if m_d:
            current_date = m_d.group(1)
            i += 1
            continue

        m_t = tm_only_re.match(l)
        if m_t and current_date:
            time_str = m_t.group(1)
            dt_val = pd.to_datetime(f"{current_date} {time_str}", dayfirst=True, errors="coerce")
            i += 1

            janela = []
            while i < len(lines) and not dt_only_re.match(lines[i]) and not tm_only_re.match(lines[i]):
                if not lines[i].startswith(("SESP -", "CENTRO POLÍTICO", "RELATÓRIO DE PESQUISA", "Impresso em", "sentry -")) and not re.match(r"^\d+/\d+$", lines[i]):
                    janela.append(lines[i])
                if len(janela) >= 6:
                    break
                i += 1

            bloco_str = " ".join(janela).replace("|", " ")
            mon = "SIM" if re.search(r"\bSIM\b", bloco_str) else "NÃO"

            placa_raw = ""
            m_pl = re.search(r"\b([A-Z]{3}-?[0-9][A-Z0-9][0-9]{2})\b", bloco_str)
            if m_pl:
                placa_raw = m_pl.group(1)
                loc_str = bloco_str.replace(placa_raw, " ", 1)
            else:
                loc_str = bloco_str

            loc_str = re.sub(r"\b(SIM|NÃO)\b\s*$", "", loc_str).strip()
            montar_registro(placa_raw, dt_val, loc_str, np.nan, np.nan, mon)
        else:
            i += 1

    return _otimizar_memoria_df(pd.DataFrame(records))


# ==============================================================================
# MOTORES DE INTELIGÊNCIA (ETAPA 1 TOP-DOWN & ETAPA 2 ROSA DOS VENTOS)
# ==============================================================================
def calcular_rosa_dos_ventos(lat1, lon1, lat2, lon2) -> str:
    if any(pd.isna(v) for v in [lat1, lon1, lat2, lon2]):
        return ""
    if abs(float(lat1) - float(lat2)) < 1e-4 and abs(float(lon1) - float(lon2)) < 1e-4:
        return ""
    phi1, phi2 = np.radians(float(lat1)), np.radians(float(lat2))
    dlambda = np.radians(float(lon2) - float(lon1))
    y = np.sin(dlambda) * np.cos(phi2)
    x = np.cos(phi1) * np.sin(phi2) - np.sin(phi1) * np.cos(phi2) * np.cos(dlambda)
    brng = (np.degrees(np.arctan2(y, x)) + 360) % 360
    setores = [
        "Norte (N)", "Nordeste (NE)", "Leste (L)", "Sudeste (SE)",
        "Sul (S)", "Sudoeste (SO)", "Oeste (O)", "Noroeste (NO)"
    ]
    idx = int((brng + 22.5) // 45) % 8
    return setores[idx]


def gerar_resumo_viagem_rosa_ventos(sub: pd.DataFrame) -> str:
    """Gera resumo objetivo por cidade/região e direção cardeal (Rosa dos Ventos)."""
    sub = sub.sort_values("timestamp").reset_index(drop=True)
    if sub.empty:
        return "Sem deslocamentos registrados."

    etapas = []
    for _, row in sub.iterrows():
        reg = str(row["regiao"])
        lat_c, lon_c = row["lat"], row["lon"]
        if not etapas:
            etapas.append({
                "regiao": reg,
                "lat_ini": lat_c,
                "lon_ini": lon_c,
                "lat_fim": lat_c,
                "lon_fim": lon_c,
                "t_ini": row["timestamp"],
                "t_fim": row["timestamp"],
            })
        else:
            if etapas[-1]["regiao"] == reg:
                if pd.notna(lat_c):
                    etapas[-1]["lat_fim"] = lat_c
                    etapas[-1]["lon_fim"] = lon_c
                etapas[-1]["t_fim"] = row["timestamp"]
            else:
                etapas.append({
                    "regiao": reg,
                    "lat_ini": lat_c,
                    "lon_ini": lon_c,
                    "lat_fim": lat_c,
                    "lon_fim": lon_c,
                    "t_ini": row["timestamp"],
                    "t_fim": row["timestamp"],
                })

    etapas_rec = etapas[-5:]
    if len(etapas_rec) == 1:
        e = etapas_rec[0]
        rumo = calcular_rosa_dos_ventos(e["lat_ini"], e["lon_ini"], e["lat_fim"], e["lon_fim"])
        rumo_txt = f" deslocando-se para *{rumo}*" if rumo else ""
        return f"Circulação concentrada em *{e['regiao']}*{rumo_txt} ({e['t_ini'].strftime('%d/%m %H:%M')} a {e['t_fim'].strftime('%d/%m %H:%M')})."

    partes = []
    for i, e in enumerate(etapas_rec):
        if i == 0:
            rumo_prox = calcular_rosa_dos_ventos(e["lat_fim"], e["lon_fim"], etapas_rec[i + 1]["lat_ini"], etapas_rec[i + 1]["lon_ini"])
            rumo_str = f" rumo *{rumo_prox}*" if rumo_prox else ""
            partes.append(f"Saiu de *{e['regiao']}*{rumo_str} ({e['t_fim'].strftime('%d/%m %H:%M')})")
        elif i < len(etapas_rec) - 1:
            rumo_prox = calcular_rosa_dos_ventos(e["lat_fim"], e["lon_fim"], etapas_rec[i + 1]["lat_ini"], etapas_rec[i + 1]["lon_ini"])
            rumo_str = f" seguindo para *{rumo_prox}*" if rumo_prox else ""
            partes.append(f"passou por *{e['regiao']}*{rumo_str}")
        else:
            rumo_ult = calcular_rosa_dos_ventos(etapas_rec[i - 1]["lat_fim"], etapas_rec[i - 1]["lon_fim"], e["lat_fim"], e["lon_fim"])
            rumo_str = f" (sentido *{rumo_ult}*)" if rumo_ult else ""
            partes.append(f"apareceu por último em *{e['regiao']}*{rumo_str} às {e['t_fim'].strftime('%d/%m %H:%M')}")

    return " -> ".join(partes) + "."


def analisar_etapa1_corredor(
    df_valid: pd.DataFrame,
    min_ocrs: int = 4,
    min_delta_min: float = 5.0,
    max_delta_min: float = 20.0,
    min_dp_min: float = 1.0,
    max_dp_min: float = 2.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Classifica alvos em deslocamento rumo a BG (Top-Down por Mais de uma Região) e detecta batedores."""
    df_v = df_valid.sort_values(["placa", "timestamp"]).reset_index(drop=True)
    for col_s in ["zona", "regiao", "arquivo", "nome", "sentido_bg", "cam_id"]:
        df_v[col_s] = df_v[col_s].astype(str)

    df_v["prev_zona"] = df_v.groupby("placa")["zona"].shift(1)
    df_v["prev_ts"] = df_v.groupby("placa")["timestamp"].shift(1)
    df_v["delta_seg_min"] = (df_v["timestamp"] - df_v["prev_ts"]).dt.total_seconds() / 60.0

    segs = df_v[df_v["prev_zona"].notna() & (df_v["zona"] != df_v["prev_zona"]) & (df_v["delta_seg_min"] <= 600)].copy()
    segs["par_zona"] = segs["prev_zona"] + "->" + segs["zona"]
    med_map = segs.groupby("par_zona")["delta_seg_min"].median().to_dict()

    alvos = []
    for placa, grp in df_v.groupby("placa"):
        grp = grp.sort_values("timestamp")
        regioes_seq = list(dict.fromkeys(grp["regiao"]))
        arquivos_seq = list(dict.fromkeys(grp["arquivo"]))
        qtd_regioes = len(regioes_seq)
        qtd_arquivos = len(arquivos_seq)

        d_ini = float(grp["dist_bg"].dropna().iloc[0]) if not grp["dist_bg"].dropna().empty else np.nan
        d_fim = float(grp["dist_bg"].dropna().iloc[-1]) if not grp["dist_bg"].dropna().empty else np.nan
        aprox_km = (d_ini - d_fim) if (pd.notna(d_ini) and pd.notna(d_fim)) else 0.0

        if aprox_km < 40:
            continue
        if grp["sentido_bg"].iloc[-1] == "AFASTAMENTO" and qtd_regioes < 2:
            continue

        t_ini = grp["timestamp"].iloc[0]
        t_fim = grp["timestamp"].iloc[-1]
        dur_min = (t_fim - t_ini).total_seconds() / 60.0
        vel_kmh = (aprox_km / (dur_min / 60.0)) if dur_min > 0 else 0.0

        ratios = []
        for idx in range(1, len(grp)):
            pz = grp["zona"].iloc[idx - 1] + "->" + grp["zona"].iloc[idx]
            dt_m = (grp["timestamp"].iloc[idx] - grp["timestamp"].iloc[idx - 1]).total_seconds() / 60.0
            if pz in med_map and med_map[pz] > 5 and dt_m > 0:
                ratios.append(dt_m / med_map[pz])

        ratio_medio = np.mean(ratios) if ratios else 1.0

        if vel_kmh >= 102 or ratio_medio <= 0.85:
            perfil = "⚡ CAVALO DOIDO (Rápido / Sem Parada)"
            fator_bg = 0.90
        elif vel_kmh <= 66 or ratio_medio >= 1.25:
            perfil = "⛽ TANQUE REDUZIDO (Lento / Abastecendo)"
            fator_bg = 1.15
        else:
            perfil = "🚗 FLUXO PADRÃO RUMO BG"
            fator_bg = 1.00

        h_min_bg = float(grp["h_min_bg"].dropna().iloc[-1]) if not grp["h_min_bg"].dropna().empty else 6.0
        h_max_bg = float(grp["h_max_bg"].dropna().iloc[-1]) if not grp["h_max_bg"].dropna().empty else 8.5

        chegada_bg_ini = t_fim + timedelta(hours=float(h_min_bg * fator_bg))
        chegada_bg_fim = t_fim + timedelta(hours=float(h_max_bg * fator_bg))

        if qtd_regioes >= 2:
            if len(regioes_seq) == 2:
                desc_regiao = f"{qtd_regioes} regiões: Saiu de {regioes_seq[0]} e apareceu em {regioes_seq[1]}"
            else:
                meio = " -> ".join(regioes_seq[1:-1])
                desc_regiao = f"{qtd_regioes} regiões: Saiu de {regioes_seq[0]} -> {meio} -> apareceu em {regioes_seq[-1]}"
        else:
            desc_regiao = f"1 região: {regioes_seq[0]}"

        alvos.append({
            "_qtd_regioes": qtd_regioes,
            "_qtd_arquivos": qtd_arquivos,
            "Placa": grp["placa_fmt"].iloc[0],
            "Mais de uma Região": desc_regiao,
            "Perfil Cinemático": perfil,
            "Leituras": len(grp),
            "Avanço Rumo BG (km)": round(aprox_km, 0),
            "Vel. Média (km/h)": round(vel_kmh, 1),
            "Último Ponto": grp["nome"].iloc[-1],
            "Última Leitura": t_fim.strftime("%d/%m %H:%M"),
            "Janela Abordagem BG": f"{chegada_bg_ini.strftime('%d/%m %H:%M')} às {chegada_bg_fim.strftime('%H:%M')}",
        })

    df_alvos = pd.DataFrame(alvos)
    if not df_alvos.empty:
        df_alvos = (
            df_alvos.sort_values(
                by=["_qtd_regioes", "_qtd_arquivos", "Avanço Rumo BG (km)", "Vel. Média (km/h)"],
                ascending=[False, False, False, False],
            )
            .drop(columns=["_qtd_regioes", "_qtd_arquivos"])
            .reset_index(drop=True)
        )

    df_ord = df_v[df_v["cam_id"] != "SEM_ID"].sort_values(["cam_id", "timestamp"]).reset_index(drop=True)
    pares = []
    for cid, grp in df_ord.groupby("cam_id"):
        recs = grp.to_dict("records")
        for i in range(len(recs)):
            for j in range(i + 1, len(recs)):
                diff_m = (recs[j]["timestamp"] - recs[i]["timestamp"]).total_seconds() / 60.0
                if diff_m > max_delta_min:
                    break
                if diff_m >= min_delta_min and recs[i]["placa"] != recs[j]["placa"]:
                    pares.append({
                        "p1": recs[i]["placa_fmt"],
                        "p2": recs[j]["placa_fmt"],
                        "cam_id": cid,
                        "ponto": str(recs[i]["nome"]),
                        "delta_min": round(diff_m, 2),
                        "t1": recs[i]["timestamp"],
                    })

    df_comboios = pd.DataFrame()
    if pares:
        df_p = pd.DataFrame(pares)
        df_p["Dupla (Batedor <-> Carga)"] = df_p.apply(lambda r: " <-> ".join(sorted([r["p1"], r["p2"]])), axis=1)
        comb = df_p.groupby("Dupla (Batedor <-> Carga)").agg(
            OCRs_Distintos=("cam_id", "nunique"),
            Intervalo_Médio_min=("delta_min", "mean"),
            Desvio_Padrão_min=("delta_min", "std"),
            Início=("t1", "min"),
            Fim=("t1", "max"),
            Pontos_Rastreados=("ponto", lambda x: " -> ".join(dict.fromkeys(x))),
        ).reset_index()

        df_comboios = comb[
            (comb["OCRs_Distintos"] >= min_ocrs)
            & (comb["Intervalo_Médio_min"] >= min_delta_min)
            & (comb["Intervalo_Médio_min"] <= max_delta_min)
            & (comb["Desvio_Padrão_min"].notna())
            & (comb["Desvio_Padrão_min"] >= min_dp_min)
            & (comb["Desvio_Padrão_min"] <= max_dp_min)
        ].sort_values(by=["OCRs_Distintos", "Desvio_Padrão_min"], ascending=[False, True]).reset_index(drop=True)

        if not df_comboios.empty:
            df_comboios["Intervalo_Médio_min"] = df_comboios["Intervalo_Médio_min"].round(2)
            df_comboios["Desvio_Padrão_min"] = df_comboios["Desvio_Padrão_min"].round(2)
            df_comboios["Início"] = df_comboios["Início"].dt.strftime("%d/%m %H:%M")
            df_comboios["Fim"] = df_comboios["Fim"].dt.strftime("%d/%m %H:%M")

    return df_alvos, df_comboios


def analisar_etapa2_individual(df_all: pd.DataFrame, placa_alvo: str) -> dict:
    """Prepara dados da lupa individual: gráfico de pizza por horário e ficha WPP enxuta."""
    sub = df_all[df_all["placa"] == placa_alvo].sort_values("timestamp").reset_index(drop=True)
    for col_s in ["regiao", "nome", "local", "arquivo"]:
        sub[col_s] = sub[col_s].astype(str)
    placa_exibicao = sub["placa_fmt"].iloc[0] if not sub.empty else placa_alvo

    bins = [0, 6, 12, 18, 24]
    turnos_labels = ["Madrugada (00h–06h)", "Manhã (06h–12h)", "Tarde (12h–18h)", "Noite (18h–24h)"]
    sub["faixa_horaria"] = pd.cut(sub["timestamp"].dt.hour, bins=bins, labels=turnos_labels, right=False)
    df_pizza = sub["faixa_horaria"].value_counts().reindex(turnos_labels, fill_value=0).reset_index()
    df_pizza.columns = ["Faixa Horária", "Passagens"]
    df_pizza = df_pizza[df_pizza["Passagens"] > 0]

    resumo_rosa = gerar_resumo_viagem_rosa_ventos(sub)

    ultimas_10 = sub.tail(10).iloc[::-1]
    linhas_10 = []
    for idx_r, (_, r) in enumerate(ultimas_10.iterrows()):
        rumo_seg = ""
        if idx_r + 1 < len(ultimas_10):
            r_ant = ultimas_10.iloc[idx_r + 1]
            az = calcular_rosa_dos_ventos(r_ant["lat"], r_ant["lon"], r["lat"], r["lon"])
            if az:
                rumo_seg = f" [{az}]"
        linhas_10.append(f"  {idx_r + 1}. {r['timestamp'].strftime('%d/%m/%Y %H:%M')} — {r['regiao']} ({r['nome']}){rumo_seg}")

    lista_10_str = "\n".join(linhas_10)

    briefing_wpp = f"""🚗 *PLACA:* {placa_exibicao}

🧭 *RESUMO DA VIAGEM (ROSA DOS VENTOS):*
{resumo_rosa}

🕒 *ÚLTIMAS 10 PASSAGENS (MAIS RECENTE NO TOPO):*
{lista_10_str}"""

    return {
        "sub": sub,
        "total_leituras": len(sub),
        "regiao_atual": sub["regiao"].iloc[-1] if not sub.empty else "-",
        "ultima_data": sub["timestamp"].iloc[-1].strftime("%d/%m/%Y %H:%M") if not sub.empty else "-",
        "df_pizza": df_pizza,
        "briefing_wpp": briefing_wpp,
    }


# ==============================================================================
# INTERFACE PRINCIPAL (SIDEBAR COM MEMÓRIA ACUMULADORA & 3 ABAS)
# ==============================================================================
if "base_dfs" not in st.session_state:
    st.session_state["base_dfs"] = {}

with st.sidebar:
    st.title("🛡️ SENTRY INTEL MT")
    st.markdown("**Corredores:** RO / Bolívia / MS $\\rightarrow$ Barra do Garças")
    st.divider()

    arquivos = st.file_uploader(
        "Adicione relatórios do Sentry (XLSX, CSV ou PDF — aceita múltiplas levas)",
        type=["csv", "pdf", "xlsx", "xls"],
        accept_multiple_files=True,
    )

    if arquivos:
        novos = 0
        for arq in arquivos:
            chave = f"{arq.name}_{arq.size}"
            if chave not in st.session_state["base_dfs"]:
                df_p = parse_arquivo_sentry(arq.name, arq.getvalue())
                if not df_p.empty:
                    st.session_state["base_dfs"][chave] = df_p
                    novos += 1
        if novos > 0:
            gc.collect()
            st.success(f"✅ +{novos} relatório(s) integrado(s) à base!")

    if st.session_state["base_dfs"]:
        st.markdown(f"**Relatórios na Base Ativa ({len(st.session_state['base_dfs'])}):**")
        for k, df_item in st.session_state["base_dfs"].items():
            nome_limpo = str(df_item["arquivo"].iloc[0])
            st.caption(f"📄 {nome_limpo} ({len(df_item):,} reg.)".replace(",", "."))

        if st.button("🗑️ Limpar Base / Nova Operação", use_container_width=True):
            st.session_state["base_dfs"] = {}
            gc.collect()
            st.rerun()

    st.divider()
    if st.button("Sair / Bloquear Tela", use_container_width=True):
        st.session_state["autenticado"] = False
        st.rerun()

tab1, tab2, tab3 = st.tabs([
    "🚨 Etapa 1: Geralzão & Abordagem BG",
    "🔍 Etapa 2: Lupa Individual & Ficha WPP",
    "📲 Calculadora H0 (Checklist WhatsApp)",
])

df_consolidado = pd.DataFrame()
if st.session_state["base_dfs"]:
    df_consolidado = pd.concat(list(st.session_state["base_dfs"].values()), ignore_index=True)
    df_consolidado = (
        df_consolidado.drop_duplicates(subset=["placa", "timestamp", "cam_id", "local"])
        .sort_values("timestamp")
        .reset_index(drop=True)
    )

# ------------------------------------------------------------------------------
# ABA 1: ETAPA 1 - GERALZÃO & INTERCEPTAÇÃO EM BARRA DO GARÇAS
# ------------------------------------------------------------------------------
with tab1:
    if df_consolidado.empty:
        st.info("👈 Suba um ou mais arquivos XLSX, CSV ou PDF do Sentry na barra lateral para iniciar a varredura.")
    else:
        df_valid = df_consolidado[df_consolidado["status_ocr"] == "VALIDA"].copy()
        df_mon = df_consolidado[df_consolidado["monitoramento"] == "SIM"]
        df_parc = df_consolidado[df_consolidado["status_ocr"] == "PARCIAL_OCR"]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Leituras Únicas Integradas", f"{len(df_consolidado):,}".replace(",", "."))
        c2.metric("Placas Válidas Únicas", f"{df_valid['placa'].nunique():,}".replace(",", "."))
        c3.metric("Alertas Monitoramento (SIM)", len(df_mon))
        c4.metric("Placas Parciais / Estrangeiras", len(df_parc))

        if not df_mon.empty:
            st.error("🚨 **ALERTA DE MONITORAMENTO ATIVO (`SIM`) DETECTADO NOS ARQUIVOS:**")
            st.dataframe(df_mon[["placa_fmt", "timestamp", "regiao", "nome", "arquivo"]], use_container_width=True)

        min_ocrs_val = st.session_state.get("min_ocrs_batedor", 4)
        tempo_val = st.session_state.get("tempo_batedor", (5.0, 20.0))
        dp_val = st.session_state.get("dp_batedor", (1.0, 2.0))

        df_alvos, df_comboios = analisar_etapa1_corredor(
            df_valid,
            min_ocrs=int(min_ocrs_val),
            min_delta_min=float(tempo_val[0]),
            max_delta_min=float(tempo_val[1]),
            min_dp_min=float(dp_val[0]),
            max_dp_min=float(dp_val[1]),
        )

        st.subheader("🎯 Alvos Rumo a Barra do Garças (Prioridade Top-Down: Mais de uma Região)")
        if df_alvos.empty:
            st.warning("Nenhum veículo com progressão líquida >= 40 km rumo a Barra do Garças encontrado neste recorte.")
        else:
            filtro_perfil = st.multiselect(
                "Filtrar por Perfil Cinemático:",
                options=df_alvos["Perfil Cinemático"].unique().tolist(),
                default=df_alvos["Perfil Cinemático"].unique().tolist(),
            )
            df_exibir = df_alvos[df_alvos["Perfil Cinemático"].isin(filtro_perfil)]
            st.dataframe(df_exibir, use_container_width=True, height=380)

        st.subheader("🗺️ Mapa Tático dos Sensores Acionados")
        geo_pts = (
            df_valid.dropna(subset=["lat", "lon"])
            .assign(nome=lambda d: d["nome"].astype(str), lat=lambda d: d["lat"].astype(float), lon=lambda d: d["lon"].astype(float))
            .groupby(["nome", "lat", "lon"], as_index=False)
            .size()
            .rename(columns={"size": "passagens"})
        )
        if not geo_pts.empty:
            geo_pts["raio"] = np.clip(geo_pts["passagens"] * 40, 3000, 18000)
            layer = pdk.Layer(
                "ScatterplotLayer",
                data=geo_pts,
                get_position="[lon, lat]",
                get_color="[255, 75, 75, 190]",
                get_radius="raio",
                pickable=True,
            )
            view = pdk.ViewState(latitude=-15.55, longitude=-56.5, zoom=5.5)
            st.pydeck_chart(pdk.Deck(layers=[layer], initial_view_state=view, tooltip={"text": "{nome}\nPassagens: {passagens}"}))

        with st.expander("🔎 Inspecionar Placas Parciais / Estrangeiras (ex.: Bolívia / OCR truncado)"):
            st.dataframe(df_parc[["placa_fmt", "timestamp", "regiao", "nome", "arquivo"]], use_container_width=True)

        st.divider()
        st.subheader("🚓 Análise de Batedores")
        f1, f2, f3 = st.columns(3)
        f1.number_input("Mínimo de OCRs Diferentes", min_value=2, max_value=10, value=4, step=1, key="min_ocrs_batedor")
        f2.slider("Intervalo entre veículos (min)", min_value=1.0, max_value=30.0, value=(5.0, 20.0), step=0.5, key="tempo_batedor")
        f3.slider("Desvio Padrão do intervalo — DP (min)", min_value=0.0, max_value=5.0, value=(1.0, 2.0), step=0.1, key="dp_batedor")

        if df_comboios.empty:
            st.caption(
                f"Nenhuma dupla encontrada com >= {min_ocrs_val} OCRs distintos, "
                f"intervalo entre {tempo_val[0]:.0f} e {tempo_val[1]:.0f} min e DP entre {dp_val[0]:.1f} e {dp_val[1]:.1f} min."
            )
        else:
            st.dataframe(df_comboios, use_container_width=True, height=300)

# ------------------------------------------------------------------------------
# ABA 2: ETAPA 2 - LUPA INDIVIDUAL & FICHA WHATSAPP PARA ABORDAGEM
# ------------------------------------------------------------------------------
with tab2:
    if df_consolidado.empty:
        st.info("👈 Suba o relatório individual da placa (ou o lote geral) na barra lateral.")
    else:
        placas_disp = df_consolidado[df_consolidado["placa"] != "SEM_LEITURA"]["placa"].value_counts()
        if placas_disp.empty:
            st.warning("⚠️ Nenhuma placa válida foi identificada neste arquivo. Inspecione os registros brutos abaixo:")
            st.dataframe(df_consolidado.head(50), use_container_width=True)
        else:
            opcoes = [f"{p} ({cnt} leituras)" for p, cnt in placas_disp.items()]
            escolha = st.selectbox("Selecione a Placa Alvo para Inspeção:", options=opcoes)
            placa_sel = escolha.split(" ")[0]

            res = analisar_etapa2_individual(df_consolidado, placa_sel)

            col_info, col_pizza = st.columns([1.1, 1.2])
            with col_info:
                st.metric("Total de Leituras Integradas", res["total_leituras"])
                st.metric("Última Região Registrada", res["regiao_atual"])
                st.metric("Última Passagem", res["ultima_data"])

            with col_pizza:
                if not res["df_pizza"].empty:
                    fig_pizza = px.pie(
                        res["df_pizza"],
                        names="Faixa Horária",
                        values="Passagens",
                        title=f"Distribuição de Horários que {placa_sel} Roda Mais",
                        hole=0.35,
                    )
                    fig_pizza.update_traces(textinfo="percent+label")
                    st.plotly_chart(fig_pizza, use_container_width=True)

            rota_geo = (
                res["sub"].dropna(subset=["lat", "lon"])
                .assign(nome=lambda d: d["nome"].astype(str), lat=lambda d: d["lat"].astype(float), lon=lambda d: d["lon"].astype(float))
                .copy()
            )
            if len(rota_geo) >= 1:
                st.subheader(f"🗺️ Trajeto Rastreado de {placa_sel}")
                pontos_unicos = rota_geo.groupby(["nome", "lat", "lon"], as_index=False).size().rename(columns={"size": "vezes"})
                layer_pts = pdk.Layer(
                    "ScatterplotLayer",
                    data=pontos_unicos,
                    get_position="[lon, lat]",
                    get_color="[0, 200, 120, 220]",
                    get_radius=8000,
                    pickable=True,
                )
                layers = [layer_pts]
                if len(rota_geo) >= 2:
                    path_coords = [[float(r["lon"]), float(r["lat"])] for _, r in rota_geo.iterrows()]
                    layer_path = pdk.Layer(
                        "PathLayer",
                        data=[{"path": path_coords, "name": placa_sel}],
                        get_path="path",
                        get_color="[255, 180, 0, 200]",
                        width_scale=20,
                        width_min_pixels=3,
                    )
                    layers.append(layer_path)
                view_ind = pdk.ViewState(latitude=float(rota_geo["lat"].mean()), longitude=float(rota_geo["lon"].mean()), zoom=5.8)
                st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=view_ind, tooltip={"text": "{nome}\nPassagens: {vezes}"}))

            st.subheader("📋 Histórico Completo de Passagens")
            st.dataframe(
                res["sub"][["timestamp", "regiao", "nome", "local", "arquivo"]].iloc[::-1],
                use_container_width=True,
            )

            st.divider()
            st.subheader("📲 Ficha Operacional para WhatsApp (Abordagem)")
            st.caption("Clique no ícone de copiar no canto superior direito da caixa abaixo para enviar à equipe.")
            st.code(res["briefing_wpp"], language="markdown")

# ------------------------------------------------------------------------------
# ABA 3: CALCULADORA OPERACIONAL H0 (CHECKLIST WHATSAPP — RO/BOLÍVIA + EIXO MS)
# ------------------------------------------------------------------------------
with tab3:
    st.subheader("📲 Gerador Automático de Consultas Sentry (Fórmula Hora Zero H0)")
    st.caption("Defina a janela inicial de saída na fronteira/divisa (H0) para calcular automaticamente todos os blocos até Barra do Garças.")

    col_d1, col_t1, col_t2 = st.columns(3)
    data_h0 = col_d1.date_input("Data Base (H0)", value=datetime.now().date())
    hora_ini = col_t1.time_input("Início Janela Origem (H0_ini)", value=datetime.strptime("06:00", "%H:%M").time())
    hora_fim = col_t2.time_input("Fim Janela Origem (H0_fim)", value=datetime.strptime("10:00", "%H:%M").time())

    h0_ini = datetime.combine(data_h0, hora_ini)
    h0_fim = datetime.combine(data_h0, hora_fim)
    if h0_fim <= h0_ini:
        h0_fim += timedelta(days=1)

    fmt = "%d/%m/%Y %H:%M"
    texto_wpp = f"""*PROTOCOLO SENTRY — RASTREIO FRONTEIRAS / DIVISAS -> BARRA DO GARÇAS*
🕒 *Base Hora Zero (H0):* {h0_ini.strftime(fmt)} até {h0_fim.strftime(fmt)}
⚠️ *REGRA:* Abrir a setinha *(>)* e marcar *somente* a sub-câmera indicada.

━━━━━━━━━━━━━━━━━━━━━━
*RELATÓRIO 1 (HORA 0): ORIGEM RO + FRONTEIRA BOLÍVIA*
📅 *Horário:* {h0_ini.strftime(fmt)} até {h0_fim.strftime(fmt)}
• *MT - CONQUISTA D'OESTE - BR-174 KM 393 + 690* -> [S] CONQUISTA D'OESTE -> PONTES E LACERDA (SAÍDA)
• *BR 174 - KM 310 REST FAZENDINHA* -> [E] CONQUISTA D'OESTE -> (DIANTEIRA) PONTES E LACERDA -> (TRASEIRA) (ENTRADA)
• *BR 174 KM 299+500 PONTES E LACERDA* -> [E] CONQUISTA D'OESTE -> PONTES E LACERDA -> (entrada)
• *BR 174 - KM 78 ENTRADA DO ARROZAL* -> [E] BIDIRECIONAL: TRASEIRA -> BOLIVIA | DIANTEIRA -> PONTES E LACERDA
• *BR 174 - KM 25 SERRA DA BORDA* -> [E] VILA BELA DA SANTÍSSIMA TRINDADE -> PONTES E LACERDA (ENTRADA)
• *PONTE DE VILA BELA* -> [E] VILA BELA - PONTE DO RIO GUAPORE -> PONTES E LACERDA (ENTRADA)
• *PONTES E LACERDA - MT-473, KM 3* -> [E] BOLÍVIA -> PONTES E LACERDA

━━━━━━━━━━━━━━━━━━━━━━
*RELATÓRIO 2: DESCIDA P. LACERDA -> P. ESPERIDIÃO -> CÁCERES*
📅 *Horário:* {(h0_ini + timedelta(hours=1)).strftime(fmt)} até {(h0_fim + timedelta(hours=3, minutes=45)).strftime(fmt)}
• *MT - PONTES E LACERDA - BR-174 KM 1 + 310* -> [S] PONTES E LACERDA -> CÁCERES (SAÍDA)
• *MT - PONTES E LACERDA - BR-174 KM 291 + 00* -> [S] PONTES E LACERDA -> CÁCERES (SAÍDA)
• *BOM FUTURO - FAZ. FELICIDADE - BR 174* -> [E] SENTIDO PORTO ESPERIDIÃO (TRASEIRO)
• *BR 174 - KM 176* -> [E] PONTES E LACERDA -> PORTO ESPERIDIÃO (ENTRADA)
• *BR 174 - KM 166* -> [S] PORTO ESPERIDIÃO -> CÁCERES (SAÍDA)
• *MT - CACERES - BR-174 KM 114 + 60* -> [E] PONTES E LACERDA -> CÁCERES (ENTRADA)
• *BR 070 KM 743+100 CACERES* -> [E] PONTES E LACERDA -> CÁCERES (ENTRADA)

━━━━━━━━━━━━━━━━━━━━━━
*RELATÓRIO 3: ARCO NORTE / CHAPADÃO (Sem Cáceres/Cuiabá)*
📅 *Horário:* {(h0_ini + timedelta(hours=2, minutes=30)).strftime(fmt)} até {(h0_fim + timedelta(hours=8, minutes=30)).strftime(fmt)}
• *BOM FUTURO - CAMPOS DE JÚLIO - BR 364 / MT 235* -> [S] CAMPOS DE JÚLIO -> SAPEZAL (TRASEIRA) (SAÍDA)
• *BOM FUTURO - CAMPO NOVO DO PARECIS - BR 364 ACESSO FAZENDA CATUCHO* -> [E] BR - 364 -> CAMPO NOVO DO PARECIS (ENTRADA)
• *CAMPO NOVO DO PARECIS - BR - 364 - OCR 01* -> [E] SENTIDO SUL (EXTERNO)
• *CAMPO NOVO DO PARECIS - BR - 364 - OCR 03* -> [E] SENTIDO SUL (EXTERNO)
• *BR 364 KM 592+000 DIAMANTINO* -> [S] DIAMANTINO -> NOBRES (SAÍDA)
• *MT - NOBRES - BR-364 KM 567 + 80* -> [S] NOBRES -> ROSÁRIO OESTE (SAIDA)
• *MT - ROSARIO OESTE - BR-364 KM 552 + 930* -> [E] NOBRES -> ROSÁRIO OESTE (INTERNO)

━━━━━━━━━━━━━━━━━━━━━━
*RELATÓRIO 4: FUNIL SERRA / CAMPO VERDE -> PRIMAVERA DO LESTE*
📅 *Horário:* {(h0_ini + timedelta(hours=6, minutes=30)).strftime(fmt)} até {(h0_fim + timedelta(hours=11)).strftime(fmt)}
• *PP04: STO A. LEVERGER: BR-364/MT, KM 386* -> [E] CUIABÁ -> JACIARA (EXTERNO)
• *PP03: CAMPO VERDE: BR-364/MT, KM 316* -> [E] CUIABÁ -> RONDONÓPOLIS (EXTERNO)
• *CAMPO VERDE - SAÍDA PRIMAVERA DO LESTE* -> [S] CAMPO VERDE -> PRIMAVERA DO LESTE (SAÍDA)
• *BR 070 KM 283+700 PRIMAVERA DO LESTE* -> [E] CAMPO VERDE -> PRIMAVERA DO LESTE (ENTRADA)
• *MT - PRIMAVERA DO LESTE - BR-70 KM 280 + 130* -> [E] PRIMAVERA DO LESTE -> BARRA DO GARÇAS (INTERNO)
• *MT - PRIMAVERA DO LESTE - BR-70 KM 278 + 140* -> [E] PRIMAVERA DO LESTE -> BARRA DO GARÇAS (INTERNO)
• *MT - PRIMAVERA DO LESTE - BR-70 KM 275 + 660* -> [E] PRIMAVERA DO LESTE -> BARRA DO GARÇAS (INTERNO)

━━━━━━━━━━━━━━━━━━━━━━
*RELATÓRIO 5: DESVIO SUL (TESOURO/GUIRATINGA) + RETA BR-070*
📅 *Horário:* {(h0_ini + timedelta(hours=9)).strftime(fmt)} até {(h0_fim + timedelta(hours=14, minutes=30)).strftime(fmt)}
• *TESOURO - RODOVIA MT - 110* -> [S] BIDIRECIONAL: TRASEIRA -> GUIRATINGA | DIANTEIRA -> TESOURO
• *GUIRATINGA - MT - 270 - SAÍDA PARA RONDONÓPOLIS* -> [S] BIDIRECIONAL (TRASEIRA -> RONDONÓPOLIS / DIANTEIRA-> GUIRATINGA)
• *GUIRATINGA - MT 270* -> [E] BIDIRECIONAL (TRASEIRA -> GUIRATINGA | DIANTEIRA-> ALCANTILADO )
• *GENERAL CARNEIRO - BR 070 KM 65* -> [S] SENTIDO BARRA DO GARÇAS (SAÍDA)

━━━━━━━━━━━━━━━━━━━━━━
*RELATÓRIO 6 (EIXO SUL — ORIGEM MS): SONORA / ITIQUIRA / CASSILÂNDIA -> BG*
📅 *Horário Entrada Divisa MS (H0):* {h0_ini.strftime(fmt)} até {h0_fim.strftime(fmt)}
• *PP01: ITIQUIRA: BR-163/MT, KM 34* -> [E] SONORA/MS -> RONDONÓPOLIS (EXTERNO) [Sentido Norte]
• *BR 163 KM 016+500 ITIQUIRA* -> [E] SONORA/MS -> RONDONÓPOLIS (EXTERNO) [Sentido Norte]
• *BR 163 KM 044+700 ITIQUIRA* -> [E] SONORA/MS -> RONDONÓPOLIS (EXTERNO) [Sentido Norte]
• *ALTO TAQUARI - MT-100* -> [S] SENTIDO NORTE (SAÍDA) [Vindo de Cassilândia/Chapadão do Sul-MS rumo Alto Araguaia/BG]

📅 *Progressão Rondonópolis -> Bifurcação BG (H0 + 01h30 a H0 + 04h00):*
• *RONDONÓPOLIS - PRAÇA DE PEDAGIO 02 - BR-364/MT, KM 214* -> [S] SENTIDO JACIARA (SAÍDA) [Rota Leste via Campo Verde/Primavera]
• *BR 364 KM 207+500 RONDONOPOLIS* -> [S] SENTIDO JACIARA (SAÍDA)
• *ALTO GARÇAS - BR-364* -> [E] PEDRA PRETA -> ALTO GARÇAS (ENTRADA) [Rota Sul via Alto Araguaia/MT-100]
• *BR 364 KM 055+500 ALTO GARCAS* -> [S] ALTO GARÇAS -> ALTO ARAGUAIA (SAÍDA) [Seguir sentido Norte na MT-100 via Torixoréu -> BG]

━━━━━━━━━━━━━━━━━━━━━━
🎯 *JANELA DE ABORDAGEM EM BARRA DO GARÇAS:*
• ⚡ *Cavalo Doido (RO/Bolívia):* {(h0_ini + timedelta(hours=10, minutes=30)).strftime(fmt)} até {(h0_fim + timedelta(hours=12)).strftime(fmt)}
• ⛽ *Tanque Reduzido (RO/Bolívia):* {(h0_ini + timedelta(hours=13, minutes=30)).strftime(fmt)} até {(h0_fim + timedelta(hours=16, minutes=30)).strftime(fmt)}
• 🛣️ *Origem Divisa MS (Itiquira/Sonora):* {(h0_ini + timedelta(hours=6, minutes=30)).strftime(fmt)} até {(h0_fim + timedelta(hours=9)).strftime(fmt)}
• 🛣️ *Origem Divisa MS (Alto Taquari/MT-100):* {(h0_ini + timedelta(hours=3, minutes=30)).strftime(fmt)} até {(h0_fim + timedelta(hours=5)).strftime(fmt)}"""

    st.code(texto_wpp, language="markdown")
