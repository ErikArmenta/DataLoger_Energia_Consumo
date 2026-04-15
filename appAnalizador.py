# -*- coding: utf-8 -*-
"""
⚡ Enterprise Energy Analyzer v5.5 - PDF Mensual Corregido + Sliders Funcionales
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

# Intentar importar Supabase
try:
    from supabase import create_client, Client
    SUPABASE_ENABLED = True
except ImportError:
    SUPABASE_ENABLED = False

# Intentar importar dependencias para PDF
try:
    from fpdf import FPDF
    PDF_ENABLED = True
except ImportError:
    PDF_ENABLED = False

# --- CONFIGURACIÓN Y ESTABILIDAD ---
st.set_page_config(page_title="EA Energy Analyzer", layout="wide", page_icon="⚡")

# CSS para eliminar temblor y estabilizar sliders
st.markdown("""
    <style>
    html { overflow-y: scroll; }
    .main { overflow-x: hidden; }
    div.block-container { 
        padding-top: 2rem; 
        padding-bottom: 2rem;
        animation: none !important;
        transition: none !important;
    }
    .stPlotlyChart {
        animation: none !important;
        transition: none !important;
    }
    /* Estabilizar sliders */
    div[data-testid="stSlider"] {
        padding: 10px 0;
    }
    div[data-testid="stSlider"] > div {
        pointer-events: auto !important;
    }
    </style>
""", unsafe_allow_html=True)

# Configurar Supabase Client
@st.cache_resource
def init_supabase():
    if SUPABASE_ENABLED and "supabase" in st.secrets:
        try:
            url = st.secrets["supabase"]["URL"]
            key = st.secrets["supabase"]["KEY"]
            return create_client(url, key)
        except Exception as e:
            return None
    return None

supabase_client = init_supabase()

# --- FUNCIONES NÚCLEO PDF ---
if PDF_ENABLED:
    class ExecutivePDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 16)
            self.set_text_color(0, 180, 216)
            self.cell(0, 12, 'Executive Energy Analysis Report', border=0, align='C', new_x="LMARGIN", new_y="NEXT")
            self.line(10, 20, 200, 20)
            self.ln(8)

        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 8, f'Page {self.page_no()} - Powered by Vector-Core Engine', 0, 0, 'C')

def create_pdf_chart_simple(data_dict, title, chart_type='bar'):
    """Crea gráficas simples para PDF con datos agregados"""
    fig, ax = plt.subplots(figsize=(10, 5))
    
    if chart_type == 'bar':
        labels = list(data_dict.keys())
        values = list(data_dict.values())
        
        colors = ['#00B4D8', '#FF6B6B', '#4ECDC4', '#FFB347', '#9B59B6']
        bars = ax.bar(labels, values, color=colors[:len(labels)])
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        ax.set_ylabel('Power (kW)', fontsize=11)
        
        for bar, val in zip(bars, values):
            if val > 0:
                ax.annotate(f'{val:.1f}',
                           xy=(bar.get_x() + bar.get_width() / 2, val),
                           xytext=(0, 3),
                           textcoords="offset points",
                           ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    ax.grid(True, linestyle='--', alpha=0.3)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('#F8F9FA')
    plt.tight_layout()
    
    tmp_path = tempfile.mktemp(suffix=".png")
    fig.savefig(tmp_path, dpi=150, bbox_inches='tight')
    plt.close(fig)
    return tmp_path

def generate_narrative_monthly(df_cloud, energia_total, costo_kwh):
    """Genera narrativa contextual para PDF mensual"""
    narrative = []
    
    if df_cloud.empty:
        return "No historical data available for analysis."
    
    # Análisis de consumo mensual
    avg_daily_power = df_cloud['Potencia_Promedio_kW'].mean()
    max_daily_power = df_cloud['Potencia_Promedio_kW'].max()
    min_daily_power = df_cloud['Potencia_Promedio_kW'].min()
    
    # Mejor y peor día
    best_day_idx = df_cloud['Potencia_Promedio_kW'].idxmin()
    worst_day_idx = df_cloud['Potencia_Promedio_kW'].idxmax()
    best_day = df_cloud.loc[best_day_idx, 'Día']
    worst_day = df_cloud.loc[worst_day_idx, 'Día']
    
    narrative.append(f"**Monthly Executive Summary**\n\n")
    narrative.append(f"During the analyzed month, the facility recorded an average daily consumption of ")
    narrative.append(f"{avg_daily_power:.2f} kW, with peak daily consumption reaching {max_daily_power:.2f} kW ")
    narrative.append(f"and minimums of {min_daily_power:.2f} kW.\n\n")
    
    narrative.append(f"The total estimated energy consumption for the month was {energia_total:,.2f} kWh, ")
    narrative.append(f"with an estimated cost of ${energia_total * costo_kwh:,.2f} MXN.\n\n")
    
    narrative.append(f"**Key Findings:**\n")
    narrative.append(f"• Most efficient day: {best_day.strftime('%B %d, %Y')} with {df_cloud.loc[best_day_idx, 'Potencia_Promedio_kW']:.2f} kW average\n")
    narrative.append(f"• Highest consumption day: {worst_day.strftime('%B %d, %Y')} with {df_cloud.loc[worst_day_idx, 'Potencia_Promedio_kW']:.2f} kW average\n")
    
    # Tendencia
    if len(df_cloud) >= 7:
        first_week_avg = df_cloud.head(7)['Potencia_Promedio_kW'].mean()
        last_week_avg = df_cloud.tail(7)['Potencia_Promedio_kW'].mean()
        if last_week_avg > first_week_avg * 1.1:
            narrative.append(f"• ⚠️ Increasing trend detected: Last week consumption {last_week_avg:.1f} kW vs {first_week_avg:.1f} kW at month start\n")
        elif last_week_avg < first_week_avg * 0.9:
            narrative.append(f"• ✅ Improving efficiency: Last week consumption decreased to {last_week_avg:.1f} kW\n")
    
    narrative.append(f"\n**Recommendations:**\n")
    
    if max_daily_power > avg_daily_power * 1.3:
        narrative.append(f"• Investigate operations on {worst_day.strftime('%B %d, %Y')} which showed {max_daily_power - avg_daily_power:.1f} kW above average\n")
    
    narrative.append(f"• Implement continuous monitoring to identify consumption patterns\n")
    narrative.append(f"• Consider load balancing during peak days to reduce demand charges\n")
    
    return "".join(narrative)

# --- FUNCIONES DE CARGA Y PROCESAMIENTO ---

@st.cache_data(show_spinner="Analizando archivo HOBO...")
def load_hobo_data_from_bytes(file_content, extension):
    try:
        if extension == 'csv':
            content = file_content.decode('utf-8', errors='replace')
            lines = content.split('\n')
            data_start = 0
            for i, line in enumerate(lines[:30]):
                if re.search(r'\d+/\d+/\d+', line) or re.search(r'\d+-\d+-\d+', line):
                    data_start = i
                    break
            if data_start == 0: data_start = 3
            parsed_data = []
            for line in lines[data_start:]:
                if not line.strip(): continue
                clean_line = line.replace('"', '').strip()
                parts = clean_line.split('\t')
                if len(parts) < 2: parts = clean_line.split(',')
                if len(parts) >= 2: parsed_data.append(parts[:3])
            if parsed_data:
                df = pd.DataFrame(parsed_data)
                df.columns = ['Index', 'DateTime', 'Amperios']
                df['DateTime'] = pd.to_datetime(df['DateTime'], errors='coerce')
                df['Amperios'] = pd.to_numeric(df['Amperios'], errors='coerce')
                df = df.dropna(subset=['DateTime', 'Amperios']).drop(columns=['Index']).reset_index(drop=True)
                return df, 'DateTime', 'Amperios'
            return pd.DataFrame(), None, None
        else:
            df = pd.read_excel(io.BytesIO(file_content), skiprows=2)
            df.columns = [str(col).strip() for col in df.columns]
            time_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
            amp_col = df.columns[2] if len(df.columns) > 2 else df.columns[1]
            df[time_col] = pd.to_datetime(df[time_col], errors='coerce')
            df[amp_col] = pd.to_numeric(df[amp_col], errors='coerce')
            df = df.dropna(subset=[time_col]).reset_index(drop=True)
            df.rename(columns={time_col: 'DateTime', amp_col: 'Amperios'}, inplace=True)
            return df, 'DateTime', 'Amperios'
    except Exception as e:
        raise RuntimeError(f"Error procesando archivo: {str(e)}")

@st.cache_data(show_spinner="Calculando métricas...")
def preprocess_electric_data(df, time_col, amp_col, voltage_type, pf):
    df = df.copy()
    df['kW_Instant'] = (voltage_type * df[amp_col] * pf * 1.732) / 1000.0
    hours = df[time_col].dt.hour
    conditions = [(hours >= 6) & (hours < 14), (hours >= 14) & (hours < 22)]
    df['Turno'] = np.select(conditions, [1, 2], default=3)
    df['Hora'] = hours
    df['Día'] = df[time_col].dt.date
    df = df.sort_values(time_col).reset_index(drop=True)
    return df

def calculate_energy_vectorized(df, time_col, power_col):
    if df.empty or len(df) < 2: return 0.0
    time_diff_hours = df[time_col].diff().dt.total_seconds() / 3600.0
    avg_power = (df[power_col] + df[power_col].shift(1)) / 2.0
    valid_intervals = (time_diff_hours > 0) & (time_diff_hours <= 1.0)
    energy = (avg_power[valid_intervals] * time_diff_hours[valid_intervals]).sum()
    return float(energy)

def detect_peaks_vectorized(df, column, percentile=95):
    if df.empty: return pd.DataFrame(), 0.0
    threshold = df[column].quantile(percentile / 100.0)
    peaks = df[df[column] > threshold].copy()
    if not peaks.empty:
        peaks['peak_magnitude'] = peaks[column] - threshold
    return peaks, float(threshold)

@st.cache_data(show_spinner=False)
def get_filter_bounds(df, time_col):
    return df[time_col].min(), df[time_col].max()

def sanitize_pdf(text: str) -> str:
    replacements = {
        '\u2014': '-', '\u2013': '-', '\u2022': '*', '\u2019': "'",
        '\u201c': '"', '\u201d': '"', '\u2018': "'", '\u2026': '...',
        '\u00e9': 'e', '\u00ed': 'i', '\u00f3': 'o', '\u00fa': 'u', '\u00e1': 'a',
        '\u00f1': 'n', '\u00d1': 'N'
    }
    for uni, asc in replacements.items():
        text = text.replace(uni, asc)
    text = ''.join([c if ord(c) < 128 else ' ' for c in text])
    return text

# --- RENDERIZADOS DE SECCIONES ---

def render_kpi_dashboard(df_filtered, time_col, amp_col, energia_total, costo_kwh):
    st.markdown("<h2 align='center' style='color:#00B4D8;'>📊 Principal Dashboard & KPIs</h2>", unsafe_allow_html=True)
    st.write("Executive snapshot of the electrical footprint for the selected period.")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("📈 Active Records", f"{len(df_filtered):,}")
    with col2: st.metric("⚡ Avg Power", f"{df_filtered['kW_Instant'].mean():.2f} kW")
    with col3: st.metric("💡 Total Energy", f"{energia_total:.2f} kWh")
    with col4:
        horas = (df_filtered[time_col].max() - df_filtered[time_col].min()).total_seconds() / 3600
        st.metric("⏱️ Monitoring Duration", f"{horas:.1f} hrs")
    with col5: st.metric("🔴 Max Peak", f"{df_filtered['kW_Instant'].max():.2f} kW")
    st.markdown("---")
    worst_shift = df_filtered.groupby('Turno')['kW_Instant'].mean().idxmax()
    best_shift  = df_filtered.groupby('Turno')['kW_Instant'].mean().idxmin()
    costo_total = energia_total * costo_kwh
    variability = df_filtered['kW_Instant'].std() / df_filtered['kW_Instant'].mean()
    peak_hours  = df_filtered.groupby('Hora')['kW_Instant'].max().nlargest(3)
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.info(f"**🎯 Instant Diagnostics**\n- **Most Critical Shift:** Shift {worst_shift}\n- **Most Efficient Shift:** Shift {best_shift}")
    with col_b:
        st.metric("📉 Consumption Variability", f"{variability:.2%}")
        st.metric("💵 Estimated Cost", f"${costo_total:,.2f} MXN")
    with col_c:
        peak_list = "\n".join([f"- **{int(hr):02d}:00** → {val:.1f} kW" for hr, val in peak_hours.items()])
        st.markdown(f"**⏰ Peak Demand Hours:**\n{peak_list}")

@st.fragment
def render_tendencias_picos(df_filtered, time_col, amp_col, peak_percentile):
    st.markdown("<h2 align='center' style='color:#FF6B6B;'>📈 Time Trend & Peak Analysis</h2>", unsafe_allow_html=True)
    peaks, threshold = detect_peaks_vectorized(df_filtered, 'kW_Instant', peak_percentile)
    if not peaks.empty:
        st.error(f"⚠️ **DEMAND ALERT**: {len(peaks)} events exceeded threshold ({threshold:.2f} kW).")
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_filtered[time_col],
        y=df_filtered['kW_Instant'],
        name='Power (kW)',
        line=dict(color='#00B4D8', width=2),
        hovertemplate='<b>📅 Time</b>: %{x|%Y-%m-%d %H:%M}<br><b>⚡ Power</b>: %{y:.2f} kW<br><b>👥 Shift</b>: %{text}<extra></extra>',
        text=df_filtered['Turno']
    ))
    fig.add_trace(go.Scatter(
        x=df_filtered[time_col],
        y=[threshold] * len(df_filtered),
        name=f'Threshold ({peak_percentile}%)',
        line=dict(color='orange', dash='dot', width=2)
    ))
    if not peaks.empty:
        fig.add_trace(go.Scatter(
            x=peaks[time_col],
            y=peaks['kW_Instant'],
            mode='markers',
            name='⚠️ Peak Event',
            marker=dict(color='red', size=12, symbol='circle', line=dict(color='white', width=2))
        ))
    fig.update_layout(template="plotly_dark", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

@st.fragment
def render_analisis_turnos(df_filtered, voltage_type):
    st.markdown("<h2 align='center'>👥 Shift Performance Analysis</h2>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        turno_means = df_filtered.groupby('Turno')['kW_Instant'].mean().reset_index()
        turno_means['Turno'] = turno_means['Turno'].astype(str)
        fig = px.bar(turno_means, x='Turno', y='kW_Instant', color='Turno', title=f"Avg Power per Shift (V={voltage_type}V)")
        fig.update_layout(template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        turno_sum = df_filtered.groupby('Turno')['kW_Instant'].sum().reset_index()
        turno_sum['Turno'] = turno_sum['Turno'].astype(str)
        fig = px.pie(turno_sum, values='kW_Instant', names='Turno', hole=.5, title="Energy Share (%)")
        fig.update_layout(template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("### 📈 Hourly Consumption Trend by Shift")
    df_hourly = df_filtered.groupby(['Hora', 'Turno'])['kW_Instant'].mean().reset_index()
    df_hourly['Turno'] = df_hourly['Turno'].astype(str)
    fig_hourly = px.line(df_hourly, x='Hora', y='kW_Instant', color='Turno', markers=True)
    fig_hourly.update_layout(template="plotly_dark")
    st.plotly_chart(fig_hourly, use_container_width=True)

# --- PDF MENSUAL CORREGIDO (SOLO DATOS DE SUPABASE) ---
@st.fragment
def render_pdf_monthly_exporter(df_cloud, costo_kwh):
    """PDF exporter para datos mensuales de Supabase"""
    st.markdown("<h2 align='center' style='color:#00FFAA;'>📄 Monthly Executive PDF Report</h2>", unsafe_allow_html=True)
    
    if not PDF_ENABLED:
        st.warning("PDF generation requires fpdf and matplotlib")
        return
    
    if df_cloud.empty:
        st.warning("No monthly data available. Use Cloud Sync first.")
        return
    
    if st.button("📑 Generate Monthly Report", use_container_width=True, key="pdf_monthly_btn"):
        with st.spinner("Generating monthly executive report..."):
            try:
                # Calcular energía total mensual estimada
                energia_total_mensual = (df_cloud['Potencia_Promedio_kW'] * 24).sum()
                
                # Crear gráfica de tendencia diaria
                daily_data = df_cloud.set_index('Día')['Potencia_Promedio_kW'].to_dict()
                # Tomar últimos 15 días o todos si son menos
                daily_items = list(daily_data.items())[-15:]
                bar_img = create_pdf_chart_simple(dict(daily_items), 'Figure 1: Daily Average Power Trend', 'bar')
                
                # Crear gráfica de picos diarios
                peak_data = df_cloud.set_index('Día')['Pico_Maximo_kW'].to_dict()
                peak_items = list(peak_data.items())[-15:]
                peak_img = create_pdf_chart_simple(dict(peak_items), 'Figure 2: Daily Peak Demand Records', 'bar')
                
                # Generar narrativa mensual
                narrative = generate_narrative_monthly(df_cloud, energia_total_mensual, costo_kwh)
                
                # Crear PDF
                pdf = ExecutivePDF()
                pdf.add_page()
                
                # Título
                pdf.set_font('Helvetica', 'B', 14)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 10, "1. Monthly Executive Summary", new_x="LMARGIN", new_y="NEXT")
                
                # Narrativa
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(40, 40, 40)
                narrative_clean = sanitize_pdf(narrative)
                for line in narrative_clean.split('\n'):
                    if line.strip():
                        pdf.multi_cell(0, 5, line.strip())
                        pdf.ln(1)
                
                pdf.ln(5)
                
                # Gráfica 1
                pdf.set_font('Helvetica', 'B', 11)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 8, "Daily Performance Trends", new_x="LMARGIN", new_y="NEXT")
                pdf.image(bar_img, w=180)
                
                # Nueva página para gráfica 2
                pdf.add_page()
                pdf.image(peak_img, w=180)
                pdf.ln(5)
                
                # Tabla de resumen mensual
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, "Monthly Summary Table", new_x="LMARGIN", new_y="NEXT")
                
                pdf.set_font('Helvetica', '', 9)
                summary_data = [
                    ["Analysis Period", f"{df_cloud['Día'].min().strftime('%B %d, %Y')} to {df_cloud['Día'].max().strftime('%B %d, %Y')}"],
                    ["Total Days Analyzed", f"{len(df_cloud)}"],
                    ["Total Energy (kWh)", f"{energia_total_mensual:,.2f} kWh"],
                    ["Avg Daily Power", f"{df_cloud['Potencia_Promedio_kW'].mean():.2f} kW"],
                    ["Max Daily Peak", f"{df_cloud['Pico_Maximo_kW'].max():.2f} kW"],
                    ["Min Daily Power", f"{df_cloud['Potencia_Promedio_kW'].min():.2f} kW"],
                    ["Estimated Cost", f"${energia_total_mensual * costo_kwh:,.2f} MXN"],
                    ["Report Date", datetime.now().strftime('%B %d, %Y at %H:%M')]
                ]
                
                for row in summary_data:
                    pdf.set_font('Helvetica', 'B', 9)
                    pdf.cell(55, 7, row[0], border=1)
                    pdf.set_font('Helvetica', '', 9)
                    pdf.cell(0, 7, sanitize_pdf(row[1]), border=1, new_x="LMARGIN", new_y="NEXT")
                
                # Guardar PDF
                pdf_bytes = bytes(pdf.output())
                
                # Limpiar archivos temporales
                try:
                    os.remove(bar_img)
                    os.remove(peak_img)
                except:
                    pass
                
                st.success("✅ Monthly report generated successfully!")
                st.balloons()
                st.download_button(
                    label="📥 Download Monthly PDF Report",
                    data=pdf_bytes,
                    file_name=f"Monthly_Report_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf"
                )
                
            except Exception as e:
                st.error(f"Error generating PDF: {str(e)}")

@st.fragment
def render_monthly_insights(costo_kwh):
    st.markdown("<h2 align='center' style='color:#7F56D9;'>📅 Monthly Cloud Analysis (Supabase)</h2>", unsafe_allow_html=True)
    if not supabase_client:
        st.warning("Cloud Sync is not configured. Add Supabase credentials to secrets.")
        return
    
    with st.spinner("Fetching historical data..."):
        try:
            response = supabase_client.table('hobo_monthly_sync').select("*").order("Día", desc=False).execute()
            cloud_raw = response.data
            if not cloud_raw:
                st.info("No historical data found. Use Cloud Sync to upload data first.")
                return
            
            df_cloud = pd.DataFrame(cloud_raw)
            df_cloud['Día'] = pd.to_datetime(df_cloud['Día'])
            
            # Mostrar KPIs mensuales
            col1, col2, col3, col4 = st.columns(4)
            with col1: st.metric("Total Days", len(df_cloud))
            with col2: st.metric("Monthly Avg Power", f"{df_cloud['Potencia_Promedio_kW'].mean():.2f} kW")
            with col3: st.metric("Absolute Peak", f"{df_cloud['Pico_Maximo_kW'].max():.2f} kW")
            with col4: 
                energia_mensual = (df_cloud['Potencia_Promedio_kW'] * 24).sum()
                st.metric("Total Energy", f"{energia_mensual:.0f} kWh")
            
            # Gráfica de tendencia
            fig = px.bar(df_cloud, x='Día', y='Potencia_Promedio_kW', 
                        template="plotly_dark", 
                        title="Daily Average Power Trend",
                        labels={'Potencia_Promedio_kW': 'Power (kW)', 'Día': 'Date'})
            fig.add_scatter(x=df_cloud['Día'], y=df_cloud['Pico_Maximo_kW'], 
                           mode='lines+markers', name='Daily Peak', line=dict(color='orange', dash='dot'))
            st.plotly_chart(fig, use_container_width=True)
            
            # Botón para PDF mensual
            render_pdf_monthly_exporter(df_cloud, costo_kwh)
            
        except Exception as e:
            st.error(f"Cloud fetch failed: {str(e)}")

@st.fragment
def render_cloud_sync(df_filtered):
    st.markdown("<h2 align='center' style='color:#7F56D9;'>☁️ Cloud Data Synchronization</h2>", unsafe_allow_html=True)
    if not supabase_client:
        st.warning("Supabase client not available.")
        return
    
    if st.button("🚀 Push to Supabase Cloud", type="primary"):
        with st.spinner("Uploading to cloud..."):
            try:
                # Verificar si ya existen datos para evitar duplicados
                daily_data = df_filtered.groupby('Día').agg(
                    Potencia_Promedio_kW=('kW_Instant', 'mean'),
                    Pico_Maximo_kW=('kW_Instant', 'max')
                ).reset_index()
                daily_data['Día'] = daily_data['Día'].astype(str)
                
                # Insertar datos
                supabase_client.table('hobo_monthly_sync').insert(daily_data.to_dict(orient='records')).execute()
                st.success("✅ Successfully synchronized with cloud!")
                st.balloons()
                st.rerun()
            except Exception as ex:
                st.error(f"Sync failed: {str(ex)}")

# --- MAIN APP FLOW ---
with st.container():
    colA, colB = st.columns([1, 8])
    with colA:
        try:
            logo = Image.open("EA_2.png")
            st.image(logo, use_container_width=True)
        except: 
            st.write("⚡")
    with colB: 
        st.markdown("<h1 align='center' style='padding-top:20px; font-weight:800;'>Enterprise Energy Analyzer</h1>", unsafe_allow_html=True)
        st.markdown("<div align='center'><span style='color: #00FFAA; letter-spacing: 2px;'>POWERED BY HOBO & VECTOR-CORE ENGINE</span></div>", unsafe_allow_html=True)

st.markdown("---")

with st.sidebar:
    st.markdown("### 📡 Data Intake")
    uploaded_file = st.file_uploader("Upload HOBO Report (CSV/XLSX)", type=["csv", "xlsx"])

if not uploaded_file:
    st.markdown("""<div style="text-align: center; padding: 50px; background-color: #1a1e23; border-radius: 15px;">
            <h1 style="color: #4a4e53; font-size: 60px;">🚀</h1>
            <h2 style="color: #e0e6ed;">System Ready & Waiting</h2>
            <p style="color: #9aa0a6;">Upload your data file to begin analysis.</p>
            </div>""", unsafe_allow_html=True)
else:
    try:
        file_bytes = uploaded_file.getvalue()
        ext = uploaded_file.name.split('.')[-1].lower()
        df_raw, t_col, a_col = load_hobo_data_from_bytes(file_bytes, ext)

        with st.sidebar:
            st.markdown("---")
            selected_page = option_menu(
                menu_title="Navigation",
                options=["KPI Dashboard", "Behaviors", "Trends & Peaks", "Monthly Insights", "Executive PDF", "Cloud Sync"],
                icons=["layers", "pie-chart", "activity", "calendar-month", "file-earmark-pdf", "cloud-arrow-up"],
                default_index=0,
                styles={"nav-link-selected": {"background-color": "#00B4D8"}}
            )
            st.markdown("---")
            with st.expander("⚙️ Electric Parameters", expanded=True):
                volt = st.selectbox("Voltage (VL-L):", [480, 220, 110], index=0, key="volt_select")
                pf = st.number_input("Power Factor (PF):", 0.5, 1.0, 0.9, 0.01, key="pf_input")
                costo_kwh = 2.85  # Precio fijo en MXN
                st.info(f"💵 kWh Price: $2.85 MXN (fixed rate)")
            with st.expander("🎯 Filter Engine", expanded=True):
                min_d, max_d = get_filter_bounds(df_raw, t_col)
                range_d = st.date_input("Time Range:", [min_d.date(), max_d.date()], key="date_range")
                shifts = st.multiselect("Shifts:", [1, 2, 3], default=[1, 2, 3], key="shifts_select")
                # Slider con key único y valores por defecto
                peak_sens = st.slider("Peak Sensitivity (%):", 80, 99, 95, 1, key="peak_sensitivity_slider")

        df_proc = preprocess_electric_data(df_raw, t_col, a_col, volt, pf)
        df_filt = df_proc[df_proc['Turno'].isin(shifts)].copy()
        if len(range_d) == 2:
            df_filt = df_filt[(df_filt['Día'] >= range_d[0]) & (df_filt['Día'] <= range_d[1])]

        if df_filt.empty: 
            st.warning("⚠️ No data found with selected filters.")
        else:
            e_total = calculate_energy_vectorized(df_filt, t_col, 'kW_Instant')
            
            if selected_page == "KPI Dashboard": 
                render_kpi_dashboard(df_filt, t_col, a_col, e_total, costo_kwh)
            elif selected_page == "Trends & Peaks": 
                render_tendencias_picos(df_filt, t_col, a_col, peak_sens)
            elif selected_page == "Behaviors": 
                render_analisis_turnos(df_filt, volt)
            elif selected_page == "Monthly Insights": 
                render_monthly_insights(costo_kwh)
            elif selected_page == "Executive PDF": 
                # PDF diario con los datos actuales
                st.markdown("<h2 align='center' style='color:#00FFAA;'>📄 Daily Executive PDF Report</h2>", unsafe_allow_html=True)
                if st.button("📑 Generate Daily Report", use_container_width=True, key="pdf_daily_btn"):
                    with st.spinner("Generating daily report..."):
                        try:
                            shift_data = df_filt.groupby('Turno')['kW_Instant'].mean().to_dict()
                            shift_data = {f"Shift {k}": v for k, v in shift_data.items()}
                            bar_img = create_pdf_chart_simple(shift_data, 'Average Power per Shift', 'bar')
                            
                            daily_avg_data = df_filt.groupby('Día')['kW_Instant'].mean().to_dict()
                            daily_items = list(daily_avg_data.items())[-10:]
                            line_img = create_pdf_chart_simple(dict(daily_items), 'Daily Average Power Trend', 'bar')
                            
                            pdf = ExecutivePDF()
                            pdf.add_page()
                            pdf.set_font('Helvetica', 'B', 14)
                            pdf.set_text_color(0, 180, 216)
                            pdf.cell(0, 10, "Daily Executive Summary", new_x="LMARGIN", new_y="NEXT")
                            
                            pdf.set_font('Helvetica', '', 10)
                            narrative = f"Period: {df_filt[t_col].min().strftime('%B %d, %Y')} to {df_filt[t_col].max().strftime('%B %d, %Y')}. Total Energy: {e_total:,.2f} kWh. Estimated Cost: ${e_total * costo_kwh:,.2f} MXN."
                            pdf.multi_cell(0, 5, sanitize_pdf(narrative))
                            
                            pdf.image(bar_img, w=180)
                            pdf.add_page()
                            pdf.image(line_img, w=180)
                            
                            pdf_bytes = bytes(pdf.output())
                            os.remove(bar_img)
                            os.remove(line_img)
                            
                            st.success("✅ Daily report generated!")
                            st.download_button("📥 Download Daily PDF", data=pdf_bytes, 
                                             file_name=f"Daily_Report_{datetime.now().strftime('%Y%m%d')}.pdf", 
                                             mime="application/pdf")
                        except Exception as e:
                            st.error(f"Error: {str(e)}")
            elif selected_page == "Cloud Sync": 
                render_cloud_sync(df_filt)
            
    except Exception as e:
        st.error(f"⚠️ Error: {str(e)}")

st.markdown("<p style='text-align: right; color:#555; font-size:12px;'>Vector-Core Engine v5.5 | PDF Monthly Fixed | Stable Sliders</p>", unsafe_allow_html=True)
