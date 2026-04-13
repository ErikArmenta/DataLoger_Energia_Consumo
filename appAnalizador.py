# -*- coding: utf-8 -*-
"""
⚡ Enterprise Energy Analyzer v5.1
Optimizado con vectorización, st.cache_data, Tabs, fragments, PDF Storyteller, Supabase y Análisis Mensual.
Developed in Python by Master Engineer Erik Armenta.
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

# Inyección de CSS para eliminar el "temblor" en diferentes navegadores
st.markdown("""
    <style>
    /* Fuerza el scrollbar permanente para evitar saltos de ancho de página */
    html { overflow-y: scroll; }
    .main { overflow-x: hidden; }
    /* Estabiliza el contenedor de bloques */
    div.block-container { padding-top: 2rem; padding-bottom: 2rem; }
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
            self.set_font('Helvetica', 'B', 18)
            self.set_text_color(0, 180, 216)
            self.cell(0, 15, 'Executive Energy Analysis Report', border=0, align='C', new_x="LMARGIN", new_y="NEXT")
            self.line(10, 25, 200, 25)
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 10, f'Page {self.page_no()} - Powered by Vector-Core Engine (Master Engineer Erik Armenta)', 0, 0, 'C')

def create_pdf_chart_image(df, x_col, y_col, title, chart_type='bar', highlight_peaks=False):
    fig, ax = plt.subplots(figsize=(10, 5))
    
    if chart_type == 'bar':
        colors = ['#00B4D8', '#FF6B6B', '#4ECDC4']
        bars = ax.bar(df[x_col].astype(str), df[y_col], color=colors[:len(df)])
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height:.2f}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3), 
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    elif chart_type == 'line':
        ax.plot(df[x_col], df[y_col], color='#00B4D8', marker='o', markersize=4, linewidth=2, label='Energy Trend')
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        if highlight_peaks:
            threshold = df[y_col].mean() * 1.2
            peaks = df[df[y_col] > threshold]
            ax.scatter(peaks[x_col], peaks[y_col], color='red', s=60, edgecolors='white', zorder=5, label='High Peaks')
            for _, row in peaks.iterrows():
                ax.annotate(f'{row[y_col]:.1f}',
                            xy=(row[x_col], row[y_col]),
                            xytext=(0, 7),
                            textcoords="offset points",
                            ha='center', va='bottom', color='red', fontsize=9, fontweight='bold')
        ax.legend()

    ax.set_xlabel(x_col, fontsize=10)
    ax.set_ylabel('Value (kW)', fontsize=10)
    plt.xticks(rotation=45 if len(df) > 10 else 0)
    ax.grid(True, linestyle='--', alpha=0.6)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    plt.tight_layout()
    
    tmp_path = tempfile.mktemp(suffix=".png")
    fig.savefig(tmp_path, dpi=150)
    plt.close(fig)
    return tmp_path

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
        '\u2014': ' - ', '\u2013': ' - ', '\u2022': '*', '\u2019': "'",
        '\u201c': '"', '\u201d': '"', '\u2018': "'", '\u2026': '...',
        '\u00e9': 'e', '\u00ed': 'i', '\u00f3': 'o', '\u00fa': 'u', '\u00e1': 'a',
    }
    for uni, asc in replacements.items():
        text = text.replace(uni, asc)
    return text.encode('latin-1', errors='replace').decode('latin-1')

# --- RENDERIZADOS DE SECCIONES ---

def render_kpi_dashboard(df_filtered, time_col, amp_col, energia_total, costo_kwh):
    st.markdown("<h2 align='center' style='color:#00B4D8;'>📊 Principal Dashboard & KPIs</h2>", unsafe_allow_html=True)
    st.write("Executive snapshot of the electrical footprint for the selected period.")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1: st.metric("📈 Active Records", f"{len(df_filtered):,}")
    with col2: st.metric("⚡ Avg Power", f"{df_filtered['kW_Instant'].mean():.2f} kW")
    with col3: st.metric("💡 Total Energy", f"{energia_total:.2f} kWh", help="Integrated numerically via Trapezoidal Rule")
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
        peak_list = "\n".join([f"- **{int(hr):02d}:00** &rarr; {val:.1f} kW" for hr, val in peak_hours.items()])
        st.markdown(f"**⏰ Peak Demand Hours:**\n{peak_list}")

@st.fragment
def render_tendencias_picos(df_filtered, time_col, amp_col, peak_percentile):
    st.markdown("<h2 align='center' style='color:#FF6B6B;'>📈 Time Trend & Peak Analysis</h2>", unsafe_allow_html=True)
    peaks, threshold = detect_peaks_vectorized(df_filtered, 'kW_Instant', peak_percentile)
    if not peaks.empty:
        st.error(f"⚠️ **DEMAND ALERT**: {len(peaks)} events exceeded threshold ({threshold:.2f} kW).")
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=df_filtered[time_col], y=df_filtered['kW_Instant'], name='Power (kW)', line=dict(color='#00B4D8', width=1.5)))
    fig.add_trace(go.Scatter(x=df_filtered[time_col], y=[threshold]*len(df_filtered), name='Threshold', line=dict(color='orange', dash='dot')))
    if not peaks.empty:
        fig.add_trace(go.Scatter(x=peaks[time_col], y=peaks['kW_Instant'], mode='markers', name='Peak Event', marker=dict(color='red', size=8)))
    fig.update_layout(template="plotly_dark", xaxis_title="Timeline", yaxis_title="Demand Power (kW)")
    st.plotly_chart(fig, use_container_width=True)

@st.fragment
def render_analisis_turnos(df_filtered, voltage_type):
    st.markdown("<h2 align='center'>👥 Shift Performance Analysis</h2>", unsafe_allow_html=True)
    col1, col2 = st.columns(2)
    with col1:
        turno_means = df_filtered.groupby('Turno')['kW_Instant'].mean().reset_index()
        turno_means['Turno'] = turno_means['Turno'].astype(str)
        fig = px.bar(turno_means, x='Turno', y='kW_Instant', color='Turno', title=f"Avg Power per Shift (V={voltage_type}V)")
        st.plotly_chart(fig, use_container_width=True)
    with col2:
        turno_sum = df_filtered.groupby('Turno')['kW_Instant'].sum().reset_index()
        turno_sum['Turno'] = turno_sum['Turno'].astype(str)
        fig = px.pie(turno_sum, values='kW_Instant', names='Turno', hole=.5, title="Energy Share (%)")
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("### 📈 Hourly Consumption Trend by Shift")
    df_hourly = df_filtered.groupby(['Hora', 'Turno'])['kW_Instant'].mean().reset_index()
    df_hourly['Turno'] = df_hourly['Turno'].astype(str)
    fig_hourly = px.line(df_hourly, x='Hora', y='kW_Instant', color='Turno', markers=True)
    fig_hourly.update_layout(template="plotly_dark")
    st.plotly_chart(fig_hourly, use_container_width=True)

@st.fragment
def render_pdf_exporter(df_filtered, energia_total_kwh, costo_kwh, time_col, report_type='daily'):
    st.markdown(f"<h2 align='center' style='color:#00FFAA;'>📄 {'Daily' if report_type=='daily' else 'Monthly'} Executive PDF Report</h2>", unsafe_allow_html=True)
    if st.button(f"Generate {'Daily' if report_type=='daily' else 'Monthly'} Report", use_container_width=True, key=f"pdf_{report_type}"):
        with st.spinner("Compiling structural narrative..."):
            try:
                if report_type == 'daily':
                    chart_bar_df = df_filtered.groupby('Turno')['kW_Instant'].mean().reset_index()
                    chart_bar_df['Label'] = chart_bar_df['Turno'].apply(lambda x: f"Shift {x}")
                    bar_img = create_pdf_chart_image(chart_bar_df, 'Label', 'kW_Instant', 'Average Power Demand per Shift (kW)')
                    line_df = df_filtered.iloc[::max(1, len(df_filtered)//15)].head(15).copy()
                    line_img = create_pdf_chart_image(line_df, time_col, 'kW_Instant', 'Power Evolution (15-Point Sample)', 'line', highlight_peaks=True)
                else:
                    chart_bar_df = df_filtered.copy()
                    chart_bar_df['Día_Str'] = chart_bar_df['Día'].astype(str)
                    bar_img = create_pdf_chart_image(chart_bar_df, 'Día_Str', 'Potencia_Promedio_kW', 'Daily Average Trend (kW)')
                    line_img = create_pdf_chart_image(df_filtered, 'Día', 'Pico_Maximo_kW', 'Historical Peak Demand Records', 'line', highlight_peaks=True)

                pdf = ExecutivePDF()
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 14)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 10, "1. Key Performance Indicators (KPI Summary)", new_x="LMARGIN", new_y="NEXT")
                
                # --- Corrección de 'Día' (con acento) para evitar KeyError ---
                date_start = df_filtered[time_col].min().strftime('%B %d, %Y') if report_type == 'daily' else df_filtered['Día'].min().strftime('%B %d, %Y')
                date_end   = df_filtered[time_col].max().strftime('%B %d, %Y') if report_type == 'daily' else df_filtered['Día'].max().strftime('%B %d, %Y')

                pdf.set_font('Helvetica', '', 11)
                pdf.set_text_color(40, 40, 40)
                narrative = sanitize_pdf(f"Report Period: {date_start} to {date_end}. Total Energy: {energia_total_kwh:,.2f} kWh.")
                pdf.multi_cell(0, 6, narrative)
                
                pdf.image(bar_img, w=180)
                pdf.add_page()
                pdf.image(line_img, w=180)

                pdf_bytes = bytes(pdf.output())
                os.remove(bar_img)
                os.remove(line_img)
                st.success("Report Compiled Successfully!")
                st.download_button(label="📥 Download PDF", data=pdf_bytes, file_name=f"Executive_{report_type}_Report.pdf", mime="application/pdf")
            except Exception as e:
                st.error(f"Error compiling PDF: {str(e)}")

@st.fragment
def render_monthly_insights(costo_kwh):
    st.markdown("<h2 align='center' style='color:#7F56D9;'>📅 Monthly Cloud Analysis (Supabase)</h2>", unsafe_allow_html=True)
    if not supabase_client:
        st.warning("Cloud Sync is not configured.")
        return
    with st.spinner("Fetching historical data..."):
        try:
            response = supabase_client.table('hobo_monthly_sync').select("*").order("Día", desc=False).execute()
            cloud_raw = response.data
            if not cloud_raw:
                st.info("No historical data found.")
                return
            df_cloud = pd.DataFrame(cloud_raw)
            df_cloud['Día'] = pd.to_datetime(df_cloud['Día'])
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("Total Days", len(df_cloud))
            with col2: st.metric("Monthly Avg Power", f"{df_cloud['Potencia_Promedio_kW'].mean():.2f} kW")
            with col3: st.metric("Absolute Peak", f"{df_cloud['Pico_Maximo_kW'].max():.2f} kW")
            st.plotly_chart(px.bar(df_cloud, x='Día', y='Potencia_Promedio_kW', template="plotly_dark"), use_container_width=True)
            energy_est_mo = (df_cloud['Potencia_Promedio_kW'] * 24).sum()
            render_pdf_exporter(df_cloud, energy_est_mo, costo_kwh, 'Día', report_type='monthly')
        except Exception as e:
            st.error(f"Cloud fetch failed: {str(e)}")

@st.fragment
def render_cloud_sync(df_filtered):
    st.markdown("<h2 align='center' style='color:#7F56D9;'>☁️ Cloud Data Synchronization</h2>", unsafe_allow_html=True)
    if st.button("🚀 Push to Supabase Cloud", type="primary"):
        with st.spinner("Uploading..."):
            try:
                daily_data = df_filtered.groupby('Día').agg(Potencia_Promedio_kW=('kW_Instant', 'mean'), Pico_Maximo_kW=('kW_Instant', 'max')).reset_index()
                daily_data['Día'] = daily_data['Día'].astype(str)
                supabase_client.table('hobo_monthly_sync').insert(daily_data.to_dict(orient='records')).execute()
                st.success("Successfully synchronized!")
            except Exception as ex:
                st.error(f"Sync failed: {str(ex)}")

# --- MAIN APP FLOW ---
with st.container():
    colA, colB = st.columns([1, 8])
    with colA:
        try:
            logo = Image.open("EA_2.png")
            st.image(logo, use_container_width=True)
        except: st.write("⚡")
    with colB: 
        st.markdown("<h1 align='center' style='padding-top:20px; font-weight:800;'>Enterprise Energy Analyzer</h1>", unsafe_allow_html=True)
        st.markdown("<div align='center'><span style='color: #00FFAA; letter-spacing: 2px;'>POWERED BY HOBO & VECTOR-CORE ENGINE</span></div>", unsafe_allow_html=True)

st.markdown("---")

with st.sidebar:
    st.markdown("### 📡 Data Intake")
    uploaded_file = st.file_uploader("Upload HOBO Report (CSV/XLSX)", type=["csv", "xlsx"])

# LÓGICA DE CONTROL: Cambiamos st.stop() por un bloque if/else para estabilidad total
if not uploaded_file:
    welcome_container = st.container()
    with welcome_container:
        st.markdown("""<div style="text-align: center; padding: 50px; background-color: #1a1e23; border-radius: 15px; border: 1px solid #333; min-height: 400px;">
                <h1 style="color: #4a4e53; font-size: 60px;">🚀</h1><h2 style="color: #e0e6ed;">System Ready & Waiting</h2>
                <p style="color: #9aa0a6; font-size: 18px; max-width: 600px; margin: 0 auto;">Upload your data file to begin. Vector-Core will process thousands of records instantly.</p><br>
                <p style="color: #00B4D8; font-weight: bold; font-size: 15px;">🐍 Developed in Python by Master Engineer Erik Armenta</p>
                <hr style="border-color:#333; margin: 20px auto; width: 50%;"><p style="color: #666; font-size: 14px;">Mastering industrial Amperage into executive insights.</p></div>""", unsafe_allow_html=True)
else:
    # Si hay archivo, procesamos normalmente
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
                volt = st.selectbox("Voltage (VL-L):", [480, 220, 110], index=0)
                pf = st.number_input("Power Factor (PF):", 0.5, 1.0, 0.9, 0.01)
                costo_kwh = st.number_input("💵 kWh Price:", 0.0, 10.0, 2.85, 0.05)
            with st.expander("🎯 Filter Engine", expanded=True):
                min_d, max_d = get_filter_bounds(df_raw, t_col)
                range_d = st.date_input("Time Range:", [min_d.date(), max_d.date()])
                shifts = st.multiselect("Shifts:", [1, 2, 3], default=[1, 2, 3])
                peak_sens = st.slider("Peak Sensitivity (%):", 80, 99, 95)

        df_proc = preprocess_electric_data(df_raw, t_col, a_col, volt, pf)
        df_filt = df_proc[df_proc['Turno'].isin(shifts)].copy()
        if len(range_d) == 2:
            df_filt = df_filt[(df_filt['Día'] >= range_d[0]) & (df_filt['Día'] <= range_d[1])]

        if df_filt.empty: 
            st.warning("No results found.")
        else:
            e_total = calculate_energy_vectorized(df_filt, t_col, 'kW_Instant')
            if selected_page == "KPI Dashboard": render_kpi_dashboard(df_filt, t_col, a_col, e_total, costo_kwh)
            elif selected_page == "Trends & Peaks": render_tendencias_picos(df_filt, t_col, a_col, peak_sens)
            elif selected_page == "Behaviors": render_analisis_turnos(df_filt, volt)
            elif selected_page == "Monthly Insights": render_monthly_insights(costo_kwh)
            elif selected_page == "Executive PDF": render_pdf_exporter(df_filt, e_total, costo_kwh, t_col, 'daily')
            elif selected_page == "Cloud Sync": render_cloud_sync(df_filt)
            
    except Exception as e:
        st.error(f"Critical error: {str(e)}")

st.markdown("<p style='text-align: right; color:#555; font-size:12px;'>Vector-Core Engine v5.1 | Supabase Cloud Edition</p>", unsafe_allow_html=True)
