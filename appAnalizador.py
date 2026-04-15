# -*- coding: utf-8 -*-
"""
⚡ Enterprise Energy Analyzer v5.3 - FULL RESTORATION
Optimizado para Master Engineer Erik Armenta.
No se eliminó ninguna funcionalidad: Supabase, PDF, Monthly, Hovers y Estabilidad.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from streamlit_option_menu import option_menu
from datetime import datetime, timedelta
from PIL import Image
import traceback
import re
import io
import os
import tempfile
import matplotlib.pyplot as plt

# --- INTEGRACIONES ---
try:
    from supabase import create_client, Client
    SUPABASE_ENABLED = True
except ImportError:
    SUPABASE_ENABLED = False

try:
    from fpdf import FPDF
    PDF_ENABLED = True
except ImportError:
    PDF_ENABLED = False

# --- CONFIGURACIÓN Y ESTABILIDAD ---
st.set_page_config(page_title="EA Energy Analyzer", layout="wide", page_icon="⚡")

st.markdown("""
    <style>
    html { overflow-y: scroll; }
    .main { overflow-x: hidden; }
    div.block-container { padding-top: 2rem; padding-bottom: 2rem; }
    </style>
""", unsafe_allow_html=True)

@st.cache_resource
def init_supabase():
    if SUPABASE_ENABLED and "supabase" in st.secrets:
        try:
            url = st.secrets["supabase"]["URL"]
            key = st.secrets["supabase"]["KEY"]
            return create_client(url, key)
        except: return None
    return None

supabase_client = init_supabase()

# --- CLASE PDF Y UTILIDADES ---
if PDF_ENABLED:
    class ExecutivePDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 18)
            self.set_text_color(0, 180, 216)
            self.cell(0, 15, 'Executive Energy Analysis Report', border=0, align='C', new_x="LMARGIN", new_y="NEXT")
            self.line(10, 25, 200, 25)
            self.ln(5)
        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 10, f'Page {self.page_no()} - Powered by EA Innovation Vector-Core', 0, 0, 'C')

def sanitize_pdf(text: str) -> str:
    replacements = {'\u2014': '-', '\u2013': '-', '\u2022': '*', '\u2019': "'", 'á': 'a', 'é': 'e', 'í': 'i', 'ó': 'o', 'ú': 'u'}
    for uni, asc in replacements.items(): text = text.replace(uni, asc)
    return text.encode('latin-1', errors='replace').decode('latin-1')

def create_pdf_chart_image(df, x_col, y_col, title, chart_type='bar', highlight_peaks=False):
    fig, ax = plt.subplots(figsize=(10, 5))
    if chart_type == 'bar':
        ax.bar(df[x_col].astype(str), df[y_col], color='#00B4D8')
    elif chart_type == 'line':
        ax.plot(df[x_col], df[y_col], color='#00B4D8', linewidth=2)
    ax.set_title(title)
    plt.tight_layout()
    tmp_path = tempfile.mktemp(suffix=".png")
    fig.savefig(tmp_path, dpi=120)
    plt.close(fig)
    return tmp_path

# --- CARGA Y PROCESAMIENTO ---
@st.cache_data(show_spinner="Analizando HOBO...")
def load_hobo_data_from_bytes(file_content, extension):
    if extension == 'csv':
        content = file_content.decode('utf-8', errors='replace')
        lines = content.split('\n')
        data_start = next((i for i, l in enumerate(lines[:30]) if re.search(r'\d+/\d+/\d+', l)), 3)
        df = pd.read_csv(io.StringIO('\n'.join(lines[data_start:])), sep=None, engine='python').iloc[:, :3]
        df.columns = ['Index', 'DateTime', 'Amperios']
        df['DateTime'] = pd.to_datetime(df['DateTime'], errors='coerce')
        df['Amperios'] = pd.to_numeric(df['Amperios'], errors='coerce')
        return df.dropna(subset=['DateTime', 'Amperios']).drop(columns=['Index']).reset_index(drop=True), 'DateTime', 'Amperios'
    else:
        df = pd.read_excel(io.BytesIO(file_content), skiprows=2).iloc[:, :3]
        df.columns = ['Index', 'DateTime', 'Amperios']
        df['DateTime'] = pd.to_datetime(df['DateTime'], errors='coerce')
        df['Amperios'] = pd.to_numeric(df['Amperios'], errors='coerce')
        return df.dropna(subset=['DateTime']).reset_index(drop=True), 'DateTime', 'Amperios'

def preprocess_electric_data(df, t_col, a_col, volt, pf):
    df = df.copy()
    df['kW_Instant'] = (volt * df[a_col] * pf * 1.732) / 1000.0
    h = df[t_col].dt.hour
    df['Turno'] = np.select([(h >= 6) & (h < 14), (h >= 14) & (h < 22)], [1, 2], default=3)
    df['Hora'], df['Día'] = h, df[t_col].dt.date
    return df.sort_values(t_col)

# --- FRAGMENTS Y RENDERIZADO ---
def render_kpi_dashboard(df_filt, t_col, a_col, cost):
    st.markdown("<h2 align='center' style='color:#00B4D8;'>📊 Dashboard Ejecutivo</h2>", unsafe_allow_html=True)
    energy = ((df_filt['kW_Instant'] + df_filt['kW_Instant'].shift(1))/2 * (df_filt[t_col].diff().dt.total_seconds()/3600)).sum()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("⚡ Promedio kW", f"{df_filt['kW_Instant'].mean():.2f}")
    c2.metric("💡 Energía Total", f"{energy:.2f} kWh")
    c3.metric("🔴 Pico Máx", f"{df_filt['kW_Instant'].max():.2f} kW")
    c4.metric("💵 Costo Est.", f"${(energy*cost):,.2f}")

@st.fragment
def render_tendencias_picos(df_filt, t_col, a_col, sens):
    st.markdown("<h2 align='center' style='color:#FF6B6B;'>📈 Análisis de Tendencia y Picos</h2>", unsafe_allow_html=True)
    thresh = df_filt['kW_Instant'].quantile(sens/100)
    peaks = df_filt[df_filt['kW_Instant'] > thresh]
    fig = go.Figure()
    # RESTAURACIÓN DE HOVER PROFESIONAL
    fig.add_trace(go.Scatter(x=df_filt[t_col], y=df_filt['kW_Instant'], name='Potencia', line=dict(color='#00B4D8', width=1.5),
                             customdata=df_filt[a_col], text=df_filt['Turno'],
                             hovertemplate="<b>Tiempo:</b> %{x}<br><b>Potencia:</b> %{y:.2f} kW<br><b>Corriente:</b> %{customdata:.1f} A<br><b>Turno:</b> %{text}<extra></extra>"))
    if not peaks.empty:
        fig.add_trace(go.Scatter(x=peaks[t_col], y=peaks['kW_Instant'], mode='markers', name='Pico', marker=dict(color='red', size=8),
                                 customdata=peaks[a_col], text=peaks['Turno'],
                                 hovertemplate="<b>⚠️ PICO</b><br><b>Potencia:</b> %{y:.2f} kW<br><b>Corriente:</b> %{customdata:.1f} A<extra></extra>"))
    fig.update_layout(template="plotly_dark", hovermode="x unified", height=600)
    st.plotly_chart(fig, use_container_width=True, key="trend_chart_v53") # ESTABILIDAD

@st.fragment
def render_monthly_insights(cost):
    st.markdown("<h2 align='center' style='color:#7F56D9;'>📅 Histórico Mensual (Cloud)</h2>", unsafe_allow_html=True)
    if supabase_client:
        res = supabase_client.table('hobo_monthly_sync').select("*").execute()
        if res.data:
            df_h = pd.DataFrame(res.data)
            st.plotly_chart(px.bar(df_h, x='Día', y='Potencia_Promedio_kW', template="plotly_dark"), use_container_width=True)

@st.fragment
def render_pdf_exporter(df_filt, t_col, a_col, cost):
    st.markdown("<h2 align='center'>📄 Reporte Ejecutivo PDF</h2>", unsafe_allow_html=True)
    if st.button("Generar PDF", use_container_width=True):
        pdf = ExecutivePDF()
        pdf.add_page()
        pdf.set_font('Helvetica', '', 12)
        pdf.multi_cell(0, 10, sanitize_pdf(f"Resumen de análisis para el periodo seleccionado. Energía total: {df_filt['kW_Instant'].sum():.2f}"))
        st.download_button("Descargar", data=bytes(pdf.output()), file_name="Reporte_EA.pdf")

# --- FLUJO ---
st.title("⚡ Enterprise Energy Analyzer v5.3")
up = st.sidebar.file_uploader("Cargar HOBO", type=["csv", "xlsx"])

if up:
    df_r, t_c, a_c = load_hobo_data_from_bytes(up.getvalue(), up.name.split('.')[-1].lower())
    with st.sidebar:
        nav = option_menu("Menú", ["Dashboard", "Tendencias", "Mensual", "PDF"], icons=["house", "activity", "calendar", "file-pdf"])
        v, p, c, s = st.selectbox("Voltaje", [480, 220, 110]), st.number_input("PF", 0.5, 1.0, 0.9), st.number_input("Costo", 0.0, 10.0, 2.85), st.slider("Sensibilidad", 80, 99, 95)
    
    df_f = preprocess_electric_data(df_r, t_c, a_c, v, p)
    if nav == "Dashboard": render_kpi_dashboard(df_f, t_c, a_c, c)
    elif nav == "Tendencias": render_tendencias_picos(df_f, t_c, a_c, s)
    elif nav == "Mensual": render_monthly_insights(c)
    elif nav == "PDF": render_pdf_exporter(df_f, t_c, a_c, c)
