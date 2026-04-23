# -*- coding: utf-8 -*-
"""
⚡ Enterprise Energy Analyzer v6.0 - MULTI-MACHINE with Supabase
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

# --- CONFIGURACIÓN Y ESTABILIDAD ---
st.set_page_config(page_title="EA Energy Analyzer - Multi-Machine", layout="wide", page_icon="⚡")

# Precio fijo kWh
COSTO_KWH = 2.40  # Precio en MXN

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

# Configurar Supabase Client
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
    """Obtiene lista de todas las máquinas desde Supabase"""
    if not supabase_client:
        return pd.DataFrame()
    try:
        response = supabase_client.table('machines').select("*").order("machine_name").execute()
        return pd.DataFrame(response.data) if response.data else pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading machines: {e}")
        return pd.DataFrame()

def add_machine(machine_name, description=""):
    """Agrega una nueva máquina"""
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
    """Elimina una máquina y todos sus datos asociados"""
    if not supabase_client:
        return False
    try:
        # Eliminar datos de la máquina
        supabase_client.table('hobo_monthly_sync').delete().eq('machine_id', machine_id).execute()
        # Eliminar la máquina
        supabase_client.table('machines').delete().eq('id', machine_id).execute()
        return True
    except Exception as e:
        st.error(f"Error deleting machine: {e}")
        return False

def save_machine_data(machine_id, daily_data):
    """Guarda datos diarios de una máquina específica"""
    if not supabase_client:
        return False
    try:
        # Primero eliminar datos existentes de esta máquina para evitar duplicados
        supabase_client.table('hobo_monthly_sync').delete().eq('machine_id', machine_id).execute()

        # Insertar nuevos datos
        records = []
        for _, row in daily_data.iterrows():
            records.append({
                "machine_id": machine_id,
                "Día": row['Día'].strftime('%Y-%m-%d') if isinstance(row['Día'], pd.Timestamp) else str(row['Día']),
                "Potencia_Promedio_kW": float(row['Potencia_Promedio_kW']),
                "Pico_Maximo_kW": float(row['Pico_Maximo_kW'])
            })

        if records:
            supabase_client.table('hobo_monthly_sync').insert(records).execute()
        return True
    except Exception as e:
        st.error(f"Error saving machine data: {e}")
        return False

def load_machine_data(machine_id):
    """Carga los datos históricos de una máquina específica"""
    if not supabase_client or not machine_id:
        return pd.DataFrame()
    try:
        response = supabase_client.table('hobo_monthly_sync').select("*").eq('machine_id', machine_id).order("Día", desc=False).execute()
        if response.data:
            df = pd.DataFrame(response.data)
            df['Día'] = pd.to_datetime(df['Día'])
            return df
        return pd.DataFrame()
    except Exception as e:
        st.error(f"Error loading machine data: {e}")
        return pd.DataFrame()

# --- FUNCIONES NÚCLEO PDF CORREGIDAS ---
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

def create_bar_chart_png(data_dict, title, xlabel='Category', ylabel='Power (kW)'):
    """Crea gráfico de barras y retorna como bytes"""
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
            ax.annotate(f'{val:.1f}',
                       xy=(bar.get_x() + bar.get_width() / 2, val),
                       xytext=(0, 3),
                       textcoords="offset points",
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

def create_line_chart_png(data_dict, title, xlabel='Date', ylabel='Power (kW)'):
    """Crea gráfico de líneas y retorna como bytes"""
    fig, ax = plt.subplots(figsize=(8, 4))

    labels = list(data_dict.keys())
    values = list(data_dict.values())

    x_pos = range(len(labels))

    ax.plot(x_pos, values, color='#00B4D8', marker='o', markersize=6, linewidth=2)
    ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
    ax.set_ylabel(ylabel, fontsize=11)
    ax.set_xlabel(xlabel, fontsize=11)

    ax.set_xticks(x_pos)
    ax.set_xticklabels(labels, rotation=45, ha='right', fontsize=8)

    if values:
        threshold = np.mean(values) * 1.2
        for i, val in enumerate(values):
            if val > threshold:
                ax.scatter(i, val, color='red', s=100, edgecolors='white', zorder=5)
                ax.annotate(f'{val:.1f}',
                           xy=(i, val),
                           xytext=(0, 10),
                           textcoords="offset points",
                           ha='center', va='bottom', color='red', fontsize=9, fontweight='bold')

    ax.grid(True, linestyle='--', alpha=0.3)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('#F8F9FA')
    plt.tight_layout()

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf

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

def render_kpi_dashboard(df_filtered, time_col, amp_col, energia_total, machine_name):
    st.markdown(f"<h2 align='center' style='color:#00B4D8;'>📊 {machine_name} - Dashboard & KPIs</h2>", unsafe_allow_html=True)
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
    costo_total = energia_total * COSTO_KWH
    variability = df_filtered['kW_Instant'].std() / df_filtered['kW_Instant'].mean()
    peak_hours  = df_filtered.groupby('Hora')['kW_Instant'].max().nlargest(3)
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

    # Aplicar filtro de rango de potencia si se proporciona
    df_display = df_filtered.copy()
    if kw_min is not None and kw_max is not None:
        df_display = df_display[(df_display['kW_Instant'] >= kw_min) & (df_display['kW_Instant'] <= kw_max)]
        st.caption(f"🔍 Showing power values between {kw_min:.1f} kW and {kw_max:.1f} kW")

    peaks, threshold = detect_peaks_vectorized(df_display, 'kW_Instant', peak_percentile)
    if not peaks.empty:
        st.error(f"⚠️ **DEMAND ALERT**: {len(peaks)} events exceeded threshold ({threshold:.2f} kW).")

    fig = go.Figure()
    # Traza principal (línea)
    fig.add_trace(go.Scatter(
        x=df_display[time_col],
        y=df_display['kW_Instant'],
        name='Power (kW)',
        line=dict(color='#00B4D8', width=2),
        hovertemplate='<b>📅 Time</b>: %{x|%Y-%m-%d %H:%M}<br><b>⚡ Power</b>: %{y:.2f} kW<br><b>👥 Shift</b>: %{text}<extra></extra>',
        text=df_display['Turno']
    ))
    # Línea del umbral
    fig.add_trace(go.Scatter(
        x=df_display[time_col],
        y=[threshold] * len(df_display),
        name=f'Threshold ({peak_percentile}%)',
        line=dict(color='orange', dash='dot', width=2)
    ))
    # Picos (marcadores rojos)
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

# --- PDF CORREGIDOS ---
def create_line_chart_with_peaks_png(df, time_col, power_col, peaks_df, title, xlabel='Date', ylabel='Power (kW)'):
    """Crea gráfico de líneas con picos marcados y etiquetados, retorna bytes"""
    fig, ax = plt.subplots(figsize=(8, 4))

    # Línea principal
    ax.plot(df[time_col], df[power_col], color='#00B4D8', linewidth=1.5, alpha=0.7)

    # Marcar y etiquetar picos
    if not peaks_df.empty:
        ax.scatter(peaks_df[time_col], peaks_df[power_col], color='red', s=80,
                   edgecolors='white', zorder=5, label='Peaks')
        for _, row in peaks_df.iterrows():
            ax.annotate(f'{row[power_col]:.1f}',
                        xy=(row[time_col], row[power_col]),
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





def render_pdf_daily(df_filt, t_col, energia_total, machine_name):
    """PDF Diario con línea temporal + top 15 picos (figura 2 solo top 15)"""
    if st.button("📑 Generate Daily Report", use_container_width=True, key="pdf_daily_btn"):
        with st.spinner("Generating daily report..."):
            try:
                # 1. Datos por turno (gráfica 1)
                shift_data = df_filt.groupby('Turno')['kW_Instant'].mean().to_dict()
                shift_data = {f"Shift {k}": v for k, v in shift_data.items()}
                bar_img = create_bar_chart_png(shift_data, 'Average Power per Shift', 'Shift', 'Power (kW)')

                # 2. Top 15 picos absolutos (para la figura 2 - línea con etiquetas)
                top15_for_line = df_filt.nlargest(15, 'kW_Instant')[['kW_Instant', t_col, 'Turno']].copy()
                # Ordenar por tiempo para que la línea no se rompa, pero los marcadores se pondrán donde ocurren
                top15_for_line = top15_for_line.sort_values(t_col)

                line_img = create_line_chart_with_peaks_png(
                    df_filt, t_col, 'kW_Instant', top15_for_line,
                    title='Power Consumption Trend with Top 15 Peaks Highlighted',
                    xlabel='Date', ylabel='Power (kW)'
                )

                # 3. Top 15 picos absolutos (gráfica de barras - figura 3)
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
                                    xytext=(0, 5), textcoords="offset points", ha='center', fontsize=8)
                ax_peaks.grid(True, linestyle='--', alpha=0.3)
                fig_peaks.patch.set_facecolor('white')
                ax_peaks.set_facecolor('#F8F9FA')
                plt.tight_layout()
                peaks_img = BytesIO()
                fig_peaks.savefig(peaks_img, format='png', dpi=150, bbox_inches='tight')
                peaks_img.seek(0)
                plt.close(fig_peaks)

                # 4. Crear PDF (resto igual)
                pdf = ExecutivePDF()
                pdf.add_page()

                # Resumen ejecutivo profesional
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

                narrative = (
                    f"Period: {fecha_inicio} to {fecha_fin}. "
                    f"Total Energy Consumed: {energia_total:,.2f} kWh. "
                    f"Estimated Cost: ${costo_total:,.2f} MXN (${COSTO_KWH}/kWh).\n\n"
                    f"Power demand analysis shows an average consumption of {df_filt['kW_Instant'].mean():.2f} kW, "
                    f"with a maximum peak of {df_filt['kW_Instant'].max():.2f} kW. "
                    f"The variability index is {df_filt['kW_Instant'].std()/df_filt['kW_Instant'].mean():.2%}, "
                    f"indicating {'high' if (df_filt['kW_Instant'].std()/df_filt['kW_Instant'].mean())>0.3 else 'moderate'} operational instability. "
                    f"The top 15 peak events are highlighted in Figures 2 and 3. "
                    f"Recommended actions: shift load scheduling and peak clipping strategies."
                )
                pdf.multi_cell(0, 6, sanitize_pdf(narrative))
                pdf.ln(5)

                # Figura 1: Potencia por turno
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, "Figure 1: Power Distribution by Shift", new_x="LMARGIN", new_y="NEXT")
                pdf.image(bar_img, x=10, w=190)

                # Figura 2: Línea temporal con los top 15 picos etiquetados
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, "Figure 2: Time Series with Top 15 Peaks Highlighted", new_x="LMARGIN", new_y="NEXT")
                pdf.image(line_img, x=10, w=190)

                # Figura 3: Top 15 picos (barras)
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, "Figure 3: Top 15 Peak Power Events (Bar Chart)", new_x="LMARGIN", new_y="NEXT")
                pdf.image(peaks_img, x=10, w=190)

                # Tabla de detalles de los picos (igual)
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

                # Tabla resumen final
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



def render_pdf_monthly(df_cloud, machine_name):
    """PDF Mensual con línea temporal de picos + top 15 días"""
    if not PDF_ENABLED:
        st.warning("PDF generation requires fpdf and matplotlib")
        return
    if df_cloud.empty:
        st.warning("No monthly data available")
        return

    if st.button("📑 Generate Monthly Report", use_container_width=True, key="pdf_monthly_btn"):
        with st.spinner("Generating monthly report..."):
            try:
                energia_mensual = (df_cloud['Potencia_Promedio_kW'] * 24).sum()

                # Gráfica 1: Tendencia diaria promedio (barras últimos 15 días)
                daily_data = df_cloud.set_index('Día')['Potencia_Promedio_kW'].to_dict()
                daily_formatted = {k.strftime('%m/%d'): v for k, v in list(daily_data.items())[-15:]}
                bar_img = create_bar_chart_png(daily_formatted, 'Daily Average Power Trend (last 15 days)', 'Date', 'Power (kW)')

                # Gráfica 2: Línea temporal con picos diarios etiquetados (umbral percentil 90)
                threshold = df_cloud['Pico_Maximo_kW'].quantile(0.90)
                peaks_month = df_cloud[df_cloud['Pico_Maximo_kW'] > threshold].copy()
                line_img = create_line_chart_with_peaks_png(
                    df_cloud, 'Día', 'Pico_Maximo_kW', peaks_month,
                    title='Daily Peak Power Trend with Highlighted High Peaks',
                    xlabel='Date', ylabel='Peak Power (kW)'
                )

                # Gráfica 3: Top 15 días con pico más alto (barras)
                top_peaks = df_cloud.nlargest(15, 'Pico_Maximo_kW')[['Día', 'Pico_Maximo_kW', 'Potencia_Promedio_kW']].copy()
                top_peaks['Fecha'] = top_peaks['Día'].dt.strftime('%Y-%m-%d')
                top_peaks = top_peaks.reset_index(drop=True)

                fig_peaks, ax_peaks = plt.subplots(figsize=(8, 5))
                y_vals = top_peaks['Pico_Maximo_kW'].values
                x_labels = [f"#{i+1}" for i in range(len(top_peaks))]
                bars = ax_peaks.bar(x_labels, y_vals, color='#FF6B6B')
                ax_peaks.set_title('Top 15 Days by Peak Power', fontsize=14, fontweight='bold')
                ax_peaks.set_ylabel('Peak Power (kW)', fontsize=11)
                ax_peaks.set_xlabel('Event Rank', fontsize=11)
                for bar, val in zip(bars, y_vals):
                    ax_peaks.annotate(f'{val:.1f}', xy=(bar.get_x() + bar.get_width()/2, val),
                                    xytext=(0, 5), textcoords="offset points", ha='center', fontsize=8)
                ax_peaks.grid(True, linestyle='--', alpha=0.3)
                fig_peaks.patch.set_facecolor('white')
                ax_peaks.set_facecolor('#F8F9FA')
                plt.tight_layout()
                peaks_img = BytesIO()
                fig_peaks.savefig(peaks_img, format='png', dpi=150, bbox_inches='tight')
                peaks_img.seek(0)
                plt.close(fig_peaks)

                # Crear PDF
                pdf = ExecutivePDF()
                pdf.add_page()

                # Resumen ejecutivo
                pdf.set_font('Helvetica', 'B', 14)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 10, f"Executive Energy Analysis Report", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(4)
                pdf.set_font('Helvetica', 'B', 12)
                pdf.cell(0, 8, f"Monthly Executive Summary - {machine_name}", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(40, 40, 40)
                fecha_inicio = df_cloud['Día'].min().strftime('%B %d, %Y')
                fecha_fin = df_cloud['Día'].max().strftime('%B %d, %Y')
                costo_total = energia_mensual * COSTO_KWH

                narrative = (
                    f"Period: {fecha_inicio} to {fecha_fin}. "
                    f"Total Energy Consumed: {energia_mensual:,.2f} kWh. "
                    f"Estimated Cost: ${costo_total:,.2f} MXN (${COSTO_KWH}/kWh).\n\n"
                    f"Monthly average daily power: {df_cloud['Potencia_Promedio_kW'].mean():.2f} kW. "
                    f"Absolute peak recorded: {df_cloud['Pico_Maximo_kW'].max():.2f} kW. "
                    f"The top 15 daily peaks are presented in Figure 3. "
                    f"A total of {len(df_cloud)} days were analyzed. "
                    f"Significant demand events occur on {top_peaks['Fecha'].iloc[0] if not top_peaks.empty else 'N/A'} and similar dates."
                )
                pdf.multi_cell(0, 6, sanitize_pdf(narrative))
                pdf.ln(5)

                # Figura 1
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, "Figure 1: Daily Average Power Trend", new_x="LMARGIN", new_y="NEXT")
                pdf.image(bar_img, x=10, w=190)

                # Figura 2
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, "Figure 2: Daily Peak Power with Highlighted High Peaks", new_x="LMARGIN", new_y="NEXT")
                pdf.image(line_img, x=10, w=190)

                # Figura 3
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, "Figure 3: Top 15 Days by Peak Power", new_x="LMARGIN", new_y="NEXT")
                pdf.image(peaks_img, x=10, w=190)

                # Tabla de detalles
                pdf.set_font('Helvetica', 'B', 9)
                pdf.cell(0, 6, "Top 15 Peak Days Details:", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', 'B', 8)
                pdf.cell(20, 6, "Rank", border=1)
                pdf.cell(40, 6, "Date", border=1)
                pdf.cell(35, 6, "Peak Power (kW)", border=1)
                pdf.cell(35, 6, "Avg Power (kW)", border=1)
                pdf.ln(6)
                pdf.set_font('Helvetica', '', 8)
                for i, row in top_peaks.iterrows():
                    pdf.cell(20, 5, f"{i+1}", border=1)
                    pdf.cell(40, 5, sanitize_pdf(row['Fecha']), border=1)
                    pdf.cell(35, 5, f"{row['Pico_Maximo_kW']:.1f}", border=1)
                    pdf.cell(35, 5, f"{row['Potencia_Promedio_kW']:.1f}", border=1)
                    pdf.ln(5)

                # Tabla resumen final
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 11)
                pdf.cell(0, 8, "Monthly Summary Table", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', '', 9)
                summary = [
                    ["Machine", machine_name],
                    ["Analysis Period", f"{fecha_inicio} to {fecha_fin}"],
                    ["Total Days", f"{len(df_cloud)}"],
                    ["Total Energy", f"{energia_mensual:,.2f} kWh"],
                    ["Avg Daily Power", f"{df_cloud['Potencia_Promedio_kW'].mean():.2f} kW"],
                    ["Max Daily Peak", f"{df_cloud['Pico_Maximo_kW'].max():.2f} kW"],
                    ["Min Daily Power", f"{df_cloud['Potencia_Promedio_kW'].min():.2f} kW"],
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
                st.success("✅ Monthly report generated successfully!")
                st.download_button(
                    label="📥 Download Monthly PDF Report",
                    data=pdf_bytes,
                    file_name=f"Monthly_Report_{machine_name}_{datetime.now().strftime('%Y%m')}.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"Error: {str(e)}")

@st.fragment
def render_monthly_insights(df_cloud, machine_name):
    st.markdown(f"<h2 align='center' style='color:#7F56D9;'>📅 Monthly Analysis - {machine_name}</h2>", unsafe_allow_html=True)

    if df_cloud.empty:
        st.info(f"No historical data found for {machine_name}. Upload data first using Cloud Sync.")
        return

    col1, col2, col3, col4 = st.columns(4)
    energia_mensual = (df_cloud['Potencia_Promedio_kW'] * 24).sum()
    with col1: st.metric("Total Days", len(df_cloud))
    with col2: st.metric("Monthly Avg Power", f"{df_cloud['Potencia_Promedio_kW'].mean():.2f} kW")
    with col3: st.metric("Absolute Peak", f"{df_cloud['Pico_Maximo_kW'].max():.2f} kW")
    with col4: st.metric("Total Energy", f"{energia_mensual:.0f} kWh")

    fig = px.bar(df_cloud, x='Día', y='Potencia_Promedio_kW',
                template="plotly_dark",
                title="Daily Average Power Trend")
    st.plotly_chart(fig, use_container_width=True)

    render_pdf_monthly(df_cloud, machine_name)

@st.fragment
def render_cloud_sync(df_filtered, machine_id, machine_name):
    st.markdown(f"<h2 align='center' style='color:#7F56D9;'>☁️ Cloud Sync - {machine_name}</h2>", unsafe_allow_html=True)

    if not supabase_client:
        st.warning("Supabase client not available.")
        return

    if df_filtered.empty:
        st.warning("No data to sync. Please upload a file first.")
        return

    if st.button("🚀 Save to Supabase Cloud", type="primary"):
        with st.spinner(f"Saving {machine_name} data..."):
            try:
                daily_data = df_filtered.groupby('Día').agg(
                    Potencia_Promedio_kW=('kW_Instant', 'mean'),
                    Pico_Maximo_kW=('kW_Instant', 'max')
                ).reset_index()

                if save_machine_data(machine_id, daily_data):
                    st.success(f"✅ {machine_name} data saved successfully!")
                    st.balloons()
                else:
                    st.error("Failed to save data")
            except Exception as ex:
                st.error(f"Sync failed: {str(ex)}")

# --- SIDEBAR DE SELECCIÓN DE MÁQUINA ---
def render_machine_selector():
    """Renderiza el selector de máquinas en el sidebar"""
    st.sidebar.markdown("### 🏭 Machine Management")

    # Obtener máquinas existentes
    machines_df = get_machines()

    # Crear nueva máquina
    with st.sidebar.expander("➕ Add New Machine", expanded=False):
        new_machine_name = st.text_input("Machine Name", key="new_machine_name")
        new_machine_desc = st.text_area("Description (optional)", key="new_machine_desc")
        if st.button("Create Machine", key="create_machine_btn"):
            if new_machine_name:
                if add_machine(new_machine_name, new_machine_desc):
                    st.success(f"Machine '{new_machine_name}' created!")
                    st.rerun()
            else:
                st.warning("Please enter a machine name")

    # Selector de máquina
    if not machines_df.empty:
        machine_options = {row['machine_name']: row['id'] for _, row in machines_df.iterrows()}
        selected_machine_name = st.sidebar.selectbox(
            "Select Machine",
            options=list(machine_options.keys()),
            key="machine_selector"
        )
        selected_machine_id = machine_options[selected_machine_name]

        # Mostrar info de máquina seleccionada
        machine_info = machines_df[machines_df['id'] == selected_machine_id].iloc[0]
        if machine_info.get('description'):
            st.sidebar.caption(f"📝 {machine_info['description']}")

        # Botón para eliminar máquina
        with st.sidebar.expander("⚠️ Delete Machine", expanded=False):
            st.warning(f"Delete '{selected_machine_name}'? This removes all its data.")
            if st.button("🗑️ Delete This Machine", key="delete_machine_btn"):
                if delete_machine(selected_machine_id):
                    st.success(f"Machine '{selected_machine_name}' deleted!")
                    st.rerun()

        return selected_machine_id, selected_machine_name
    else:
        st.sidebar.info("No machines created yet. Add one above!")
        return None, None

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
        st.markdown("<div align='center'><span style='color: #00FFAA; letter-spacing: 2px;'>POWERED BY HOBO & VECTOR-CORE ENGINE | MULTI-MACHINE</span></div>", unsafe_allow_html=True)

st.markdown("---")

# --- SIDEBAR Y SELECCIÓN DE MÁQUINA ---
machine_id, machine_name = render_machine_selector()

# Si no hay máquina seleccionada, mostrar mensaje
if not machine_id:
    st.markdown("""<div style="text-align: center; padding: 50px; background-color: #1a1e23; border-radius: 15px;">
            <h1 style="color: #4a4e53; font-size: 60px;">🏭</h1>
            <h2 style="color: #e0e6ed;">No Machine Selected</h2>
            <p style="color: #9aa0a6;">Create a machine in the sidebar to start analyzing data.</p>
            </div>""", unsafe_allow_html=True)
else:
    # Sidebar para carga de archivos y parámetros
    with st.sidebar:
        st.markdown(f"### 📡 Upload Data - {machine_name}")
        uploaded_file = st.file_uploader(f"Upload HOBO Report for {machine_name} (CSV/XLSX)", type=["csv", "xlsx"], key=f"upload_{machine_id}")

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
            st.info(f"💵 kWh Price: ${COSTO_KWH} MXN (fixed)")
        with st.expander("🎯 Filter Engine", expanded=True):
            peak_sens = st.slider("Peak Sensitivity (%):", 80, 99, 95, 1)

    # Procesar archivo si está subido
    if not uploaded_file:
        st.markdown(f"""<div style="text-align: center; padding: 50px; background-color: #1a1e23; border-radius: 15px;">
                <h1 style="color: #4a4e53; font-size: 60px;">📁</h1>
                <h2 style="color: #e0e6ed;">Upload Data for {machine_name}</h2>
                <p style="color: #9aa0a6;">Upload a HOBO CSV/XLSX file to begin analysis.</p>
                </div>""", unsafe_allow_html=True)
    else:
        try:
            file_bytes = uploaded_file.getvalue()
            ext = uploaded_file.name.split('.')[-1].lower()
            df_raw, t_col, a_col = load_hobo_data_from_bytes(file_bytes, ext)

            df_proc = preprocess_electric_data(df_raw, t_col, a_col, volt, pf)

            # Filtros de fecha y turnos
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
                e_total = calculate_energy_vectorized(df_filt, t_col, 'kW_Instant')

                # Cargar datos históricos de la máquina para Monthly Insights
                historical_data = load_machine_data(machine_id)

                if selected_page == "KPI Dashboard":
                    render_kpi_dashboard(df_filt, t_col, a_col, e_total, machine_name)
                elif selected_page == "Trends & Peaks":
                    # Agregar control de rango de potencia solo para esta página
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
                elif selected_page == "Behaviors":
                    render_analisis_turnos(df_filt, volt)
                elif selected_page == "Monthly Insights":
                    render_monthly_insights(historical_data, machine_name)
                elif selected_page == "Executive PDF":
                    st.markdown(f"<h2 align='center' style='color:#00FFAA;'>📄 Daily Executive PDF Report - {machine_name}</h2>", unsafe_allow_html=True)
                    render_pdf_daily(df_filt, t_col, e_total, machine_name)
                elif selected_page == "Cloud Sync":
                    render_cloud_sync(df_filt, machine_id, machine_name)

        except Exception as e:
            st.error(f"⚠️ Error: {str(e)}")

st.markdown("<p style='text-align: right; color:#555; font-size:12px;'>Vector-Core Engine v6.0 | Multi-Machine | Rate: $2.40/kWh</p>", unsafe_allow_html=True)
