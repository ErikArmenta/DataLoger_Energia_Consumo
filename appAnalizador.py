# -*- coding: utf-8 -*-
"""
⚡ Enterprise Energy Analyzer v8.2 - FULL DATA LOGGING, JSON FIXED, FLOATING BUTTON
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from streamlit_option_menu import option_menu
from datetime import datetime, timedelta, date
from PIL import Image
import traceback
import re
import io
import json
import matplotlib.pyplot as plt
from io import BytesIO



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

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="EA Energy Analyzer", layout="wide", page_icon="⚡")
COSTO_KWH = 2.40

# CSS para eliminar temblor
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
    </style>
""", unsafe_allow_html=True)

# --- SUPABASE ---
@st.cache_resource
def init_supabase():
    if SUPABASE_ENABLED and "supabase" in st.secrets:
        try:
            url = st.secrets["supabase"]["URL"]
            key = st.secrets["supabase"]["KEY"]
            return create_client(url, key)
        except Exception as e:
            st.error(f"Supabase connection error: {e}")
            return None
    return None

supabase_client = init_supabase()

# --- FUNCIONES DE GESTIÓN DE MÁQUINAS ---
def get_machines():
    if not supabase_client:
        return pd.DataFrame()
    try:
        response = supabase_client.table('machines').select("*").order("machine_name").execute()
        return pd.DataFrame(response.data) if response.data else pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading machines: {e}")
        return pd.DataFrame()

def add_machine(machine_name, description=""):
    if not supabase_client:
        return False
    try:
        supabase_client.table('machines').insert({
            "machine_name": machine_name,
            "description": description,
            "created_at": datetime.now().isoformat()
        }).execute()
        return True
    except Exception as e:
        st.error(f"Error adding machine: {e}")
        return False

def delete_machine(machine_id):
    if not supabase_client:
        return False
    try:
        supabase_client.table('machine_saved_data').delete().eq('machine_id', machine_id).execute()
        supabase_client.table('machines').delete().eq('id', machine_id).execute()
        return True
    except Exception as e:
        st.error(f"Error deleting machine: {e}")
        return False

# # --- FUNCIÓN DE CONVERSIÓN A TIPOS NATIVOS (SOLUCIÓN DEFINITIVA) ---
# def convert_to_serializable(obj):
#     """Convierte recursivamente numpy/pandas a tipos nativos Python."""
#     # Si es un array de NumPy, convertirlo a lista recursivamente
#     if isinstance(obj, np.ndarray):
#         return [convert_to_serializable(x) for x in obj.tolist()]
#     # Escalares NumPy
#     if isinstance(obj, (np.integer, np.int64, np.int32)):
#         return int(obj)
#     if isinstance(obj, (np.floating, np.float64, np.float32)):
#         return float(obj)
#     if isinstance(obj, np.bool_):
#         return bool(obj)
#     # Fechas
#     if isinstance(obj, (pd.Timestamp, datetime, date)):
#         return obj.isoformat()
#     # Manejo de NaN/NaT (evita error con arrays)
#     try:
#         if pd.isna(obj):
#             return None
#     except Exception:
#         pass
#     # Listas y tuplas
#     if isinstance(obj, (list, tuple)):
#         return [convert_to_serializable(item) for item in obj]
#     # Diccionarios
#     if isinstance(obj, dict):
#         return {k: convert_to_serializable(v) for k, v in obj.items()}
#     # Cualquier otro tipo (string, int, float, etc.) se devuelve directamente
#     return obj

def save_full_machine_data(machine_id, df):
    """Guarda DataFrame como CSV en Supabase. Sin errores de serialización."""
    if not supabase_client:
        return False
    try:
        # Convertir machine_id a int nativo de Python
        machine_id = int(machine_id)
        # Convertir DataFrame a CSV (string)
        csv_data = df.to_csv(index=False)
        # Crear payload con tipos nativos
        payload = {
            "machine_id": machine_id,
            "data_json": csv_data,  # la columna se llama data_json pero contiene CSV
            "updated_at": datetime.now().isoformat()
        }
        supabase_client.table('machine_saved_data').upsert(payload, on_conflict="machine_id").execute()
        return True
    except Exception as e:
        st.error(f"Error saving data: {str(e)}")
        return False

def load_full_machine_data(machine_id):
    """Carga DataFrame desde CSV almacenado."""
    if not supabase_client:
        return pd.DataFrame()
    try:
        machine_id = int(machine_id)
        response = supabase_client.table('machine_saved_data').select("data_json").eq('machine_id', machine_id).execute()
        if response.data and len(response.data) > 0:
            csv_data = response.data[0]['data_json']
            from io import StringIO
            df = pd.read_csv(StringIO(csv_data))
            # Reconvertir columnas de fecha/hora
            for col in ['DateTime', 'Día']:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce')
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()



# --- FUNCIONES DE CARGA Y PROCESAMIENTO DE HOBO ---
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
            if data_start == 0:
                data_start = 3
            parsed_data = []
            for line in lines[data_start:]:
                if not line.strip():
                    continue
                clean_line = line.replace('"', '').strip()
                parts = clean_line.split('\t')
                if len(parts) < 2:
                    parts = clean_line.split(',')
                if len(parts) >= 2:
                    parsed_data.append(parts[:3])
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
    if df.empty or len(df) < 2:
        return 0.0
    time_diff_hours = df[time_col].diff().dt.total_seconds() / 3600.0
    avg_power = (df[power_col] + df[power_col].shift(1)) / 2.0
    valid_intervals = (time_diff_hours > 0) & (time_diff_hours <= 1.0)
    energy = (avg_power[valid_intervals] * time_diff_hours[valid_intervals]).sum()
    return float(energy)

def detect_peaks_vectorized(df, column, percentile=95):
    if df.empty:
        return pd.DataFrame(), 0.0
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
def render_kpi_dashboard(df_filtered, time_col, amp_col, energia_total, machine_name):
    st.markdown(f"<h2 align='center' style='color:#00B4D8;'>📊 {machine_name} - Dashboard & KPIs</h2>", unsafe_allow_html=True)
    st.write("Executive snapshot of the electrical footprint for the selected period.")
    col1, col2, col3, col4, col5 = st.columns(5)
    with col1:
        st.metric("📈 Active Records", f"{len(df_filtered):,}")
    with col2:
        st.metric("⚡ Avg Power", f"{df_filtered['kW_Instant'].mean():.2f} kW")
    with col3:
        st.metric("💡 Total Energy", f"{energia_total:.2f} kWh")
    with col4:
        horas = (df_filtered[time_col].max() - df_filtered[time_col].min()).total_seconds() / 3600
        st.metric("⏱️ Monitoring Duration", f"{horas:.1f} hrs")
    with col5:
        st.metric("🔴 Max Peak", f"{df_filtered['kW_Instant'].max():.2f} kW")
    st.markdown("---")
    worst_shift = df_filtered.groupby('Turno')['kW_Instant'].mean().idxmax()
    best_shift = df_filtered.groupby('Turno')['kW_Instant'].mean().idxmin()
    costo_total = energia_total * COSTO_KWH
    variability = df_filtered['kW_Instant'].std() / df_filtered['kW_Instant'].mean()
    peak_hours = df_filtered.groupby('Hora')['kW_Instant'].max().nlargest(3)
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        st.info(f"**🎯 Instant Diagnostics**\n- **Most Critical Shift:** Shift {worst_shift}\n- **Most Efficient Shift:** Shift {best_shift}")
    with col_b:
        st.metric("📉 Consumption Variability", f"{variability:.2%}")
        st.metric("💵 Estimated Cost", f"${costo_total:,.2f} MXN @ ${COSTO_KWH}/kWh")
    with col_c:
        peak_list = "\n".join([f"- **{int(hr):02d}:00** → {val:.1f} kW" for hr, val in peak_hours.items()])
        st.markdown(f"**⏰ Peak Demand Hours:**\n{peak_list}")

@st.fragment
def render_tendencias_picos(df_filtered, time_col, amp_col, peak_percentile, kw_min=None, kw_max=None):
    st.markdown("<h2 align='center' style='color:#FF6B6B;'>📈 Time Trend & Peak Analysis</h2>", unsafe_allow_html=True)
    df_display = df_filtered.copy()
    if kw_min is not None and kw_max is not None:
        df_display = df_display[(df_display['kW_Instant'] >= kw_min) & (df_display['kW_Instant'] <= kw_max)]
        st.caption(f"🔍 Showing power values between {kw_min:.1f} kW and {kw_max:.1f} kW")
    peaks, threshold = detect_peaks_vectorized(df_display, 'kW_Instant', peak_percentile)
    if not peaks.empty:
        st.error(f"⚠️ **DEMAND ALERT**: {len(peaks)} events exceeded threshold ({threshold:.2f} kW).")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df_display[time_col],
        y=df_display['kW_Instant'],
        name='Power (kW)',
        line=dict(color='#00B4D8', width=2),
        hovertemplate='<b>📅 Time</b>: %{x|%Y-%m-%d %H:%M}<br><b>⚡ Power</b>: %{y:.2f} kW<br><b>👥 Shift</b>: %{text}<extra></extra>',
        text=df_display['Turno']
    ))
    fig.add_trace(go.Scatter(
        x=df_display[time_col],
        y=[threshold] * len(df_display),
        name=f'Threshold ({peak_percentile}%)',
        line=dict(color='orange', dash='dot', width=2)
    ))
    if not peaks.empty:
        fig.add_trace(go.Scatter(
            x=peaks[time_col],
            y=peaks['kW_Instant'],
            mode='markers+text',
            name='⚠️ Peak Event',
            text=peaks['kW_Instant'].round(1).astype(str) + ' kW',
            textposition='top center',
            textfont=dict(color='red', size=10, family='Arial Black'),
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

# --- FUNCIONES PARA GRÁFICOS PNG (PDF) ---
def create_bar_chart_png(data_dict, title, xlabel='Category', ylabel='Power (kW)'):
    fig, ax = plt.subplots(figsize=(8, 4))
    labels = list(data_dict.keys())
    values = list(data_dict.values())
    colors = ['#00B4D8', '#FF6B6B', '#4ECDC4', '#FFB347', '#9B59B6']
    bars = ax.bar(labels, values, color=colors[:len(labels)])
    ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_xlabel(xlabel, fontsize=11)
    for bar, val in zip(bars, values):
        if val > 0:
            ax.annotate(f'{val:.1f}', xy=(bar.get_x() + bar.get_width()/2, val),
                        xytext=(0, 3), textcoords="offset points",
                        ha='center', va='bottom', fontsize=9, fontweight='bold')
    ax.grid(True, linestyle='--', alpha=0.3)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('#F8F9FA')
    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf

def create_line_chart_with_peaks_png(df, time_col, power_col, peaks_df, title, xlabel='Date', ylabel='Power (kW)'):
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.plot(df[time_col], df[power_col], color='#00B4D8', linewidth=1.5, alpha=0.7)
    if not peaks_df.empty:
        ax.scatter(peaks_df[time_col], peaks_df[power_col], color='red', s=80,
                   edgecolors='white', zorder=5, label='Peaks')
        for _, row in peaks_df.iterrows():
            ax.annotate(f'{row[power_col]:.1f}', xy=(row[time_col], row[power_col]),
                        xytext=(0, 10), textcoords="offset points",
                        ha='center', fontsize=8, color='red', fontweight='bold')
    ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_xlabel(xlabel, fontsize=11)
    ax.grid(True, linestyle='--', alpha=0.3)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('#F8F9FA')
    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf

if PDF_ENABLED:
    class ExecutivePDF(FPDF):
        def header(self):
            self.set_font('Helvetica', 'B', 16)
            self.set_text_color(0, 180, 216)
            self.cell(0, 12, 'Executive Energy Analysis Report', border=0, align='C')
            self.ln(8)
            self.line(10, 25, 200, 25)
            self.ln(10)
        def footer(self):
            self.set_y(-15)
            self.set_font('Helvetica', 'I', 8)
            self.set_text_color(128, 128, 128)
            self.cell(0, 8, f'Page {self.page_no()} - Powered by Vector-Core Engine', 0, 0, 'C')

def render_pdf_daily(df_filt, t_col, energia_total, machine_name):
    if st.button("📑 Generate Daily Report", use_container_width=True, key="pdf_daily_btn"):
        with st.spinner("Generating daily report..."):
            try:
                shift_data = df_filt.groupby('Turno')['kW_Instant'].mean().to_dict()
                shift_data = {f"Shift {k}": v for k, v in shift_data.items()}
                bar_img = create_bar_chart_png(shift_data, 'Average Power per Shift', 'Shift', 'Power (kW)')
                top15_for_line = df_filt.nlargest(15, 'kW_Instant')[['kW_Instant', t_col, 'Turno']].copy()
                top15_for_line = top15_for_line.sort_values(t_col)
                line_img = create_line_chart_with_peaks_png(
                    df_filt, t_col, 'kW_Instant', top15_for_line,
                    title='Power Consumption Trend with Top 15 Peaks Highlighted',
                    xlabel='Date', ylabel='Power (kW)'
                )
                top_peaks = df_filt.nlargest(15, 'kW_Instant')[['kW_Instant', t_col, 'Turno']].copy()
                top_peaks['Fecha_Hora'] = top_peaks[t_col].dt.strftime('%Y-%m-%d %H:%M')
                top_peaks = top_peaks.reset_index(drop=True)
                fig_peaks, ax_peaks = plt.subplots(figsize=(8, 5))
                y_vals = top_peaks['kW_Instant'].values
                x_labels = [f"#{i+1}" for i in range(len(top_peaks))]
                bars = ax_peaks.bar(x_labels, y_vals, color='#FF6B6B')
                ax_peaks.set_title('Top 15 Peak Power Events', fontsize=14, fontweight='bold')
                ax_peaks.set_ylabel('Power (kW)', fontsize=11)
                ax_peaks.set_xlabel('Event Rank', fontsize=11)
                for bar, val in zip(bars, y_vals):
                    ax_peaks.annotate(f'{val:.1f}', xy=(bar.get_x() + bar.get_width()/2, val),
                                      xytext=(0, 5), textcoords="offset points",
                                      ha='center', fontsize=8)
                ax_peaks.grid(True, linestyle='--', alpha=0.3)
                fig_peaks.patch.set_facecolor('white')
                ax_peaks.set_facecolor('#F8F9FA')
                plt.tight_layout()
                peaks_img = BytesIO()
                fig_peaks.savefig(peaks_img, format='png', dpi=150, bbox_inches='tight')
                peaks_img.seek(0)
                plt.close(fig_peaks)
                pdf = ExecutivePDF()
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 14)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 10, f"Executive Energy Analysis Report", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(4)
                pdf.set_font('Helvetica', 'B', 12)
                pdf.cell(0, 8, f"Daily Executive Summary - {machine_name}", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(40, 40, 40)
                fecha_inicio = df_filt[t_col].min().strftime('%B %d, %Y')
                fecha_fin = df_filt[t_col].max().strftime('%B %d, %Y')
                costo_total = energia_total * COSTO_KWH
                narrative = (f"Period: {fecha_inicio} to {fecha_fin}. "
                             f"Total Energy Consumed: {energia_total:,.2f} kWh. "
                             f"Estimated Cost: ${costo_total:,.2f} MXN (${COSTO_KWH}/kWh).\n\n"
                             f"Power demand analysis shows an average consumption of {df_filt['kW_Instant'].mean():.2f} kW, "
                             f"with a maximum peak of {df_filt['kW_Instant'].max():.2f} kW. "
                             f"The variability index is {df_filt['kW_Instant'].std()/df_filt['kW_Instant'].mean():.2%}, "
                             f"indicating {'high' if (df_filt['kW_Instant'].std()/df_filt['kW_Instant'].mean())>0.3 else 'moderate'} operational instability. "
                             f"The top 15 peak events are highlighted in Figures 2 and 3. "
                             f"Recommended actions: shift load scheduling and peak clipping strategies.")
                pdf.multi_cell(0, 6, sanitize_pdf(narrative))
                pdf.ln(5)
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, "Figure 1: Power Distribution by Shift", new_x="LMARGIN", new_y="NEXT")
                pdf.image(bar_img, x=10, w=190)
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, "Figure 2: Time Series with Top 15 Peaks Highlighted", new_x="LMARGIN", new_y="NEXT")
                pdf.image(line_img, x=10, w=190)
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, "Figure 3: Top 15 Peak Power Events (Bar Chart)", new_x="LMARGIN", new_y="NEXT")
                pdf.image(peaks_img, x=10, w=190)
                pdf.set_font('Helvetica', 'B', 9)
                pdf.cell(0, 6, "Peak Event Details (sorted by magnitude):", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', 'B', 8)
                pdf.cell(20, 6, "Rank", border=1)
                pdf.cell(50, 6, "Date & Time", border=1)
                pdf.cell(30, 6, "Power (kW)", border=1)
                pdf.cell(30, 6, "Shift", border=1)
                pdf.ln(6)
                pdf.set_font('Helvetica', '', 8)
                for i, row in top_peaks.iterrows():
                    pdf.cell(20, 5, f"{i+1}", border=1)
                    pdf.cell(50, 5, sanitize_pdf(row['Fecha_Hora']), border=1)
                    pdf.cell(30, 5, f"{row['kW_Instant']:.1f}", border=1)
                    pdf.cell(30, 5, f"{row['Turno']}", border=1)
                    pdf.ln(5)
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, "Executive Summary Table", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', '', 9)
                summary = [
                    ["Machine", machine_name],
                    ["Analysis Period", f"{fecha_inicio} to {fecha_fin}"],
                    ["Total Records", f"{len(df_filt):,}"],
                    ["Total Energy", f"{energia_total:,.2f} kWh"],
                    ["Average Power", f"{df_filt['kW_Instant'].mean():.2f} kW"],
                    ["Maximum Peak", f"{df_filt['kW_Instant'].max():.2f} kW"],
                    ["Energy Cost", f"${costo_total:,.2f} MXN"],
                    ["Rate per kWh", f"${COSTO_KWH} MXN"],
                    ["Report Date", datetime.now().strftime('%B %d, %Y at %H:%M')]
                ]
                for row in summary:
                    pdf.set_font('Helvetica', 'B', 9)
                    pdf.cell(55, 7, row[0], border=1)
                    pdf.set_font('Helvetica', '', 9)
                    pdf.cell(0, 7, sanitize_pdf(row[1]), border=1, new_x="LMARGIN", new_y="NEXT")
                pdf_bytes = bytes(pdf.output())
                st.success("✅ Daily report generated successfully!")
                st.download_button(
                    label="📥 Download Daily PDF Report",
                    data=pdf_bytes,
                    file_name=f"Daily_Report_{machine_name}_{datetime.now().strftime('%Y%m%d')}.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"Error: {str(e)}")

# --- SIDEBAR DE GESTIÓN DE MÁQUINAS ---


# --- MAIN APP ---
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
        st.markdown("<div align='center'><span style='color: #00FFAA; letter-spacing: 2px;'>POWERED BY HOBO & VECTOR-CORE ENGINE | FULL DATA LOGGING</span></div>", unsafe_allow_html=True)

st.markdown("---")

# --- SIDEBAR ---


# --- CONTENEDOR FLOTANTE CON ARRASTRE Y MINIMIZABLE (con gestión de máquinas) ---
from streamlit_floating_container import FloatingContainer

data_panel = FloatingContainer(
    icon=":material/database:",
    label="Data Manager",
    start_position="bottom",
    key="floating_data_panel",
    glassmorphic=True,
)

with data_panel.panel():
    st.markdown("### 🗄️ Data Manager")
    machines_df = get_machines()

    # Selector de máquina (si existe alguna)
    if not machines_df.empty:
        selected_machine_name = st.selectbox(
            "🏭 Select Machine",
            options=machines_df['machine_name'].tolist(),
            key="floating_machine_select"
        )
        selected_machine_id = machines_df[machines_df['machine_name'] == selected_machine_name]['id'].iloc[0]
    else:
        selected_machine_name = None
        selected_machine_id = None
        st.info("No machines available. Create one below.")

    # Botones para guardar/cargar datos (solo si hay máquina seleccionada)
    if selected_machine_id is not None:
        col_save, col_load = st.columns(2)
        with col_save:
            if st.button("💾 Save Current Data", key="floating_save_btn", use_container_width=True):
                if 'current_df' in st.session_state and st.session_state.current_df is not None:
                    if save_full_machine_data(selected_machine_id, st.session_state.current_df):
                        st.success("Data saved successfully!")
                        st.balloons()
                    else:
                        st.error("Failed to save data")
                else:
                    st.warning("No data to save. Please upload a CSV first.")
        with col_load:
            if st.button("📂 Load Machine Data", key="floating_load_btn", use_container_width=True):
                with st.spinner("Loading data..."):
                    loaded_df = load_full_machine_data(selected_machine_id)
                    if not loaded_df.empty:
                        st.session_state.current_df = loaded_df
                        st.success(f"Data for '{selected_machine_name}' loaded!")
                        st.rerun()
                    else:
                        st.warning(f"No saved data found for '{selected_machine_name}'.")
        st.divider()

    # Gestión de máquinas (añadir y eliminar)
    with st.expander("➕ Add New Machine", expanded=False):
        new_machine_name = st.text_input("Machine Name", key="new_machine_name_floating")
        new_machine_desc = st.text_area("Description (optional)", key="new_machine_desc_floating")
        if st.button("Create Machine", key="create_machine_btn_floating"):
            if new_machine_name:
                if add_machine(new_machine_name, new_machine_desc):
                    st.success(f"Machine '{new_machine_name}' created!")
                    st.rerun()
            else:
                st.warning("Please enter a machine name")

    if not machines_df.empty:
        with st.expander("⚠️ Delete Machine", expanded=False):
            machine_to_delete = st.selectbox(
                "Select machine to delete",
                machines_df['machine_name'].tolist(),
                key="delete_machine_select_floating"
            )
            if st.button("🗑️ Delete Selected Machine", key="delete_machine_btn_floating"):
                machine_id = machines_df[machines_df['machine_name'] == machine_to_delete]['id'].iloc[0]
                if delete_machine(machine_id):
                    st.success(f"Machine '{machine_to_delete}' deleted!")
                    st.rerun()

# --- ÁREA PRINCIPAL: UPLOAD Y VISUALIZACIÓN ---
if 'current_df' not in st.session_state:
    st.session_state.current_df = None

with st.sidebar:
    st.markdown("### ⚙️ Electric Parameters")
    volt = st.selectbox("Voltage (VL-L):", [480, 220, 110], index=0)
    pf = st.number_input("Power Factor (PF):", 0.5, 1.0, 0.9, 0.01)
    st.info(f"💵 kWh Price: ${COSTO_KWH} MXN")
    peak_sens = st.slider("Peak Sensitivity (%):", 80, 99, 95, 1, key="peak_sens_global")

selected_page = option_menu(
    menu_title=None,
    options=["KPI Dashboard", "Behaviors", "Trends & Peaks", "Executive PDF"],
    icons=["layers", "pie-chart", "activity", "file-earmark-pdf"],
    default_index=0,
    styles={"nav-link-selected": {"background-color": "#00B4D8"}},
    orientation="horizontal"
)

uploaded_file = st.file_uploader("📁 Upload HOBO Report (CSV/XLSX)", type=["csv", "xlsx"], key="main_uploader")

if uploaded_file is not None:
    try:
        file_bytes = uploaded_file.getvalue()
        ext = uploaded_file.name.split('.')[-1].lower()
        df_raw, t_col, a_col = load_hobo_data_from_bytes(file_bytes, ext)
        df_proc = preprocess_electric_data(df_raw, t_col, a_col, volt, pf)
        min_d, max_d = get_filter_bounds(df_proc, t_col)
        with st.sidebar:
            with st.expander("🎯 Filter Engine", expanded=True):
                range_d = st.date_input("Time Range:", [min_d.date(), max_d.date()], key="date_range")
                shifts = st.multiselect("Shifts:", [1, 2, 3], default=[1, 2, 3], key="shifts")
        df_filt = df_proc[df_proc['Turno'].isin(shifts)].copy()
        if len(range_d) == 2:
            df_filt = df_filt[(df_filt['Día'] >= range_d[0]) & (df_filt['Día'] <= range_d[1])]
        if df_filt.empty:
            st.warning("⚠️ No data found with selected filters.")
        else:
            st.session_state.current_df = df_filt
            e_total = calculate_energy_vectorized(df_filt, t_col, 'kW_Instant')
            try:
                machine_name = selected_machine_name
            except:
                machine_name = "Current Machine"
            if selected_page == "KPI Dashboard":
                render_kpi_dashboard(df_filt, t_col, a_col, e_total, machine_name)
            elif selected_page == "Behaviors":
                render_analisis_turnos(df_filt, volt)
            elif selected_page == "Trends & Peaks":
                with st.sidebar:
                    with st.expander("📊 Filter by Power Range", expanded=False):
                        min_kw = float(df_filt['kW_Instant'].min())
                        max_kw = float(df_filt['kW_Instant'].max())
                        kw_range = st.slider(
                            "kW Range to display:",
                            min_value=min_kw,
                            max_value=max_kw,
                            value=(min_kw, max_kw),
                            step=0.5,
                            key="kw_range_filter"
                        )
                render_tendencias_picos(df_filt, t_col, a_col, peak_sens, kw_range[0], kw_range[1])
            elif selected_page == "Executive PDF":
                st.markdown(f"<h2 align='center' style='color:#00FFAA;'>📄 Daily Executive PDF Report</h2>", unsafe_allow_html=True)
                render_pdf_daily(df_filt, t_col, e_total, machine_name)
    except Exception as e:
        st.error(f"⚠️ Error: {str(e)}")
else:
    if st.session_state.current_df is not None:
        df_filt = st.session_state.current_df
        t_col = 'DateTime' if 'DateTime' in df_filt.columns else df_filt.columns[0]
        e_total = calculate_energy_vectorized(df_filt, t_col, 'kW_Instant')
        try:
            machine_name = selected_machine_name
        except:
            machine_name = "Loaded Machine"
        if selected_page == "KPI Dashboard":
            render_kpi_dashboard(df_filt, t_col, 'Amperios', e_total, machine_name)
        elif selected_page == "Behaviors":
            render_analisis_turnos(df_filt, volt)
        elif selected_page == "Trends & Peaks":
            with st.sidebar:
                with st.expander("📊 Filter by Power Range", expanded=False):
                    min_kw = float(df_filt['kW_Instant'].min())
                    max_kw = float(df_filt['kW_Instant'].max())
                    kw_range = st.slider(
                        "kW Range to display:",
                        min_value=min_kw,
                        max_value=max_kw,
                        value=(min_kw, max_kw),
                        step=0.5,
                        key="kw_range_filter"
                    )
            render_tendencias_picos(df_filt, t_col, 'Amperios', peak_sens, kw_range[0], kw_range[1])
        elif selected_page == "Executive PDF":
            render_pdf_daily(df_filt, t_col, e_total, machine_name)
    else:
        st.info("📂 Upload a CSV file or load data from a machine using the floating button.")

st.markdown("<p style='text-align: right; color:#555; font-size:12px;'>Desarrollado por Master Ingeniero Erik Armenta | Vector-Core Engine v8.2 | Full Data Logging | Tarifa: $2.40/kWh</p>", unsafe_allow_html=True)
