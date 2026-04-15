# -*- coding: utf-8 -*-
"""
⚡ Enterprise Energy Analyzer v5.2 - FULL STABLE EDITION
Optimizado para Master Engineer Erik Armenta.
Restauración de Hovers, Estabilización de Gráficas y Narrativa PDF.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from streamlit_option_menu import option_menu
from datetime import datetime
from PIL import Image
import traceback
import re
import io
import os
import tempfile
import matplotlib.pyplot as plt

# --- CONFIGURACIÓN DE INTEGRACIONES ---
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

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="EA Energy Analyzer", layout="wide", page_icon="⚡")

# Inyección de CSS para estabilidad visual
st.markdown("""
    <style>
    html { overflow-y: scroll; }
    .main { overflow-x: hidden; }
    div.block-container { padding-top: 2rem; padding-bottom: 2rem; }
    </style>
""", unsafe_allow_html=True)

# --- INICIALIZACIÓN SUPABASE ---
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

# --- CLASE PDF EJECUTIVA ---
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
            self.cell(0, 10, f'Page {self.page_no()} - EA Innovation Vector-Core Engine', 0, 0, 'C')

def sanitize_pdf(text: str) -> str:
    replacements = {'\u2014': '-', '\u2013': '-', '\u2022': '*', '\u2019': "'", '\u00e1': 'a', '\u00e9': 'e', '\u00ed': 'i', '\u00f3': 'o', '\u00fa': 'u'}
    for uni, asc in replacements.items(): text = text.replace(uni, asc)
    return text.encode('latin-1', errors='replace').decode('latin-1')

def create_pdf_chart_image(df, x_col, y_col, title, chart_type='bar', highlight_peaks=False):
    fig, ax = plt.subplots(figsize=(10, 5))
    if chart_type == 'bar':
        ax.bar(df[x_col].astype(str), df[y_col], color='#00B4D8')
    elif chart_type == 'line':
        ax.plot(df[x_col], df[y_col], color='#00B4D8', linewidth=2)
        if highlight_peaks:
            p_val = df[y_col].max()
            ax.annotate(f'Peak: {p_val:.1f}', xy=(df[x_col].iloc[df[y_col].idxmax()], p_val), color='red')
    ax.set_title(title)
    plt.tight_layout()
    tmp_path = tempfile.mktemp(suffix=".png")
    fig.savefig(tmp_path, dpi=100)
    plt.close(fig)
    return tmp_path

# --- PROCESAMIENTO DE DATOS ---
@st.cache_data(show_spinner="Processing HOBO Data...")
def load_hobo_data_from_bytes(file_content, extension):
    try:
        if extension == 'csv':
            content = file_content.decode('utf-8', errors='replace')
            lines = content.split('\n')
            data_start = 0
            for i, line in enumerate(lines[:30]):
                if re.search(r'\d+/\d+/\d+', line):
                    data_start = i
                    break
            df = pd.read_csv(io.StringIO('\n'.join(lines[data_start:])), sep=None, engine='python')
            df = df.iloc[:, :3]
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
    except Exception as e: raise RuntimeError(f"Error: {str(e)}")

def preprocess_electric_data(df, time_col, amp_col, voltage_type, pf):
    df = df.copy()
    df['kW_Instant'] = (voltage_type * df[amp_col] * pf * 1.732) / 1000.0
    df['Turno'] = np.select([(df[time_col].dt.hour >= 6) & (df[time_col].dt.hour < 14), (df[time_col].dt.hour >= 14) & (df[time_col].dt.hour < 22)], [1, 2], default=3)
    df['Hora'] = df[time_col].dt.hour
    df['Día'] = df[time_col].dt.date
    return df.sort_values(time_col)

def detect_peaks_vectorized(df, column, percentile=95):
    threshold = df[column].quantile(percentile / 100.0)
    return df[df[column] > threshold].copy(), float(threshold)

# --- COMPONENTES DE INTERFAZ ---
def render_kpi_dashboard(df_filtered, t_col, a_col, cost):
    st.markdown("<h2 align='center' style='color:#00B4D8;'>📊 Enterprise Dashboard</h2>", unsafe_allow_html=True)
    energy = ((df_filtered['kW_Instant'] + df_filtered['kW_Instant'].shift(1))/2 * (df_filtered[t_col].diff().dt.total_seconds()/3600)).sum()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("⚡ Avg Power", f"{df_filtered['kW_Instant'].mean():.2f} kW")
    c2.metric("💡 Total Energy", f"{energy:.2f} kWh")
    c3.metric("🔴 Max Peak", f"{df_filtered['kW_Instant'].max():.2f} kW")
    c4.metric("💵 Est. Cost", f"${(energy*cost):,.2f}")

@st.fragment
def render_tendencias_picos(df_filtered, t_col, a_col, peak_sens):
    st.markdown("<h2 align='center' style='color:#FF6B6B;'>📈 Advanced Trend Analysis</h2>", unsafe_allow_html=True)
    peaks, threshold = detect_peaks_vectorized(df_filtered, 'kW_Instant', peak_sens)
    fig = go.Figure()
    # RESTAURACIÓN DE HOVER PROFESIONAL
    fig.add_trace(go.Scatter(x=df_filtered[t_col], y=df_filtered['kW_Instant'], name='Demand (kW)', line=dict(color='#00B4D8', width=1.5),
                             customdata=df_filtered[a_col], text=df_filtered['Turno'],
                             hovertemplate="<b>Time:</b> %{x}<br><b>Power:</b> %{y:.2f} kW<br><b>Current:</b> %{customdata:.1f} A<br><b>Shift:</b> %{text}<extra></extra>"))
    fig.add_hline(y=threshold, line_dash="dot", line_color="orange", annotation_text="Peak Threshold")
    if not peaks.empty:
        fig.add_trace(go.Scatter(x=peaks[t_col], y=peaks['kW_Instant'], mode='markers', name='Peak Alert', marker=dict(color='red', size=8),
                                 customdata=peaks[a_col], text=peaks['Turno'],
                                 hovertemplate="<b>⚠️ PEAK</b><br><b>Value:</b> %{y:.2f} kW<br><b>Current:</b> %{customdata:.1f} A<extra></extra>"))
    fig.update_layout(template="plotly_dark", hovermode="x unified", height=600)
    st.plotly_chart(fig, use_container_width=True, key="master_chart_energy") # KEY PARA EVITAR PARPADEO

@st.fragment
def render_pdf_exporter(df_filtered, t_col, a_col, cost, report_type='daily'):
    st.markdown("<h2 align='center' style='color:#00FFAA;'>📄 Executive PDF Engine</h2>", unsafe_allow_html=True)
    if st.button("Generate Executive Report", use_container_width=True):
        with st.spinner("Building Narrative..."):
            # LÓGICA NARRATIVA INGENIERIL
            avg_p = df_filtered['kW_Instant'].mean()
            energy = ((df_filtered['kW_Instant'] + df_filtered['kW_Instant'].shift(1))/2 * (df_filtered[t_col].diff().dt.total_seconds()/3600)).sum()
            
            pdf = ExecutivePDF()
            pdf.add_page()
            pdf.set_font('Helvetica', 'B', 14)
            pdf.cell(0, 10, "1. System Performance Summary", new_x="LMARGIN", new_y="NEXT")
            pdf.set_font('Helvetica', '', 11)
            narrative = f"Analysis performed from {df_filtered[t_col].min()} to {df_filtered[t_col].max()}. " \
                        f"The operation maintained an average demand of {avg_p:.2f} kW, totaling {energy:.2f} kWh. " \
                        f"At a rate of ${cost}/kWh, the estimated cost is ${energy*cost:,.2f}."
            pdf.multi_cell(0, 7, sanitize_pdf(narrative))
            
            bar_img = create_pdf_chart_image(df_filtered.groupby('Turno')['kW_Instant'].mean().reset_index(), 'Turno', 'kW_Instant', 'Avg Power by Shift')
            pdf.image(bar_img, w=170)
            
            st.download_button("📥 Download PDF", data=bytes(pdf.output()), file_name="Executive_Energy_Report.pdf")

# --- FLUJO PRINCIPAL ---
st.title("⚡ Enterprise Energy Analyzer v5.2")
uploaded_file = st.sidebar.file_uploader("Upload HOBO Data", type=["csv", "xlsx"])

if not uploaded_file:
    st.info("System Ready. Please upload a HOBO file to initiate Vector-Core processing.")
else:
    df_raw, t_col, a_col = load_hobo_data_from_bytes(uploaded_file.getvalue(), uploaded_file.name.split('.')[-1].lower())
    
    with st.sidebar:
        nav = option_menu("Navigation", ["Dashboard", "Trends & Peaks", "Executive PDF"], icons=["speedometer", "activity", "file-pdf"], default_index=0)
        volt = st.selectbox("Voltage (V):", [480, 220, 110], index=0)
        pf = st.number_input("PF:", 0.5, 1.0, 0.9)
        cost = st.number_input("Cost/kWh:", 0.0, 10.0, 2.85)
        sens = st.slider("Peak Sensitivity:", 80, 99, 95)

    df_filt = preprocess_electric_data(df_raw, t_col, a_col, volt, pf)
    
    if nav == "Dashboard": render_kpi_dashboard(df_filt, t_col, a_col, cost)
    elif nav == "Trends & Peaks": render_tendencias_picos(df_filt, t_col, a_col, sens)
    elif nav == "Executive PDF": render_pdf_exporter(df_filt, t_col, a_col, cost)

st.markdown("<p align='right' style='color:#444;'>Vector-Core Engine | Developed by Erik Armenta</p>", unsafe_allow_html=True)
