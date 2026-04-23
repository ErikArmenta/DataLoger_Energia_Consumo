# -*- coding: utf-8 -*-
"""
⚡ Enterprise Energy Analyzer v6.1 - MULTI-MACHINE with Supabase
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
        supabase_client.table('hobo_monthly_sync').delete().eq('machine_id', machine_id).execute()
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
        supabase_client.table('hobo_monthly_sync').delete().eq('machine_id', machine_id).execute()
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

# --- FUNCIONES NÚCLEO PDF ---
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
            self.cell(0, 8, f'Page {self.page_no()} - Vector-Core Engine v6.1 | EA Enterprise Energy Analyzer', 0, 0, 'C')

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

# --- NUEVAS FUNCIONES GRÁFICAS TÉCNICAS ---

def create_pie_chart_png(data_dict, title):
    """Crea gráfico de torta con porcentajes y retorna como bytes"""
    fig, ax = plt.subplots(figsize=(6, 5))
    labels = list(data_dict.keys())
    values = list(data_dict.values())
    colors = ['#00B4D8', '#FF6B6B', '#4ECDC4', '#FFB347', '#9B59B6']
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct='%1.1f%%',
        colors=colors[:len(labels)], startangle=90,
        wedgeprops=dict(edgecolor='white', linewidth=2)
    )
    for at in autotexts:
        at.set_fontsize(10)
        at.set_fontweight('bold')
    ax.set_title(title, fontsize=13, fontweight='bold', pad=12)
    fig.patch.set_facecolor('white')
    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf

def create_technical_series_png(df, time_col, title):
    """Serie de tiempo técnica con banda de variabilidad +-1sigma, media y umbral P95"""
    fig, ax = plt.subplots(figsize=(8, 4))
    values = df['kW_Instant'].values
    avg = values.mean()
    std = values.std()
    threshold_95 = np.percentile(values, 95)
    n = max(1, len(df) // 600)
    df_plot = df.iloc[::n]
    x_idx = list(range(len(df_plot)))
    ax.plot(x_idx, df_plot['kW_Instant'].values, color='#00B4D8', linewidth=1.2, alpha=0.85, label='Power (kW)')
    ax.axhline(avg, color='#2ECC71', linestyle='--', linewidth=1.8, label=f'Mean: {avg:.2f} kW')
    ax.axhline(avg + std, color='#F39C12', linestyle=':', linewidth=1.2, label=f'+1s: {avg+std:.2f} kW')
    ax.axhline(threshold_95, color='#E74C3C', linestyle='--', linewidth=1.8, label=f'P95: {threshold_95:.2f} kW')
    ax.fill_between(x_idx, avg - std, avg + std, alpha=0.12, color='#2ECC71')
    ax.set_title(title, fontsize=13, fontweight='bold', pad=12)
    ax.set_ylabel('Power (kW)', fontsize=10)
    ax.set_xlabel('Time (sampled points)', fontsize=10)
    ax.legend(fontsize=8, loc='upper right', framealpha=0.9)
    ax.grid(True, linestyle='--', alpha=0.3)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('#F8F9FA')
    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf

def create_hourly_avg_png(df, title):
    """Potencia promedio por hora 0-23 con codigo de colores por nivel"""
    fig, ax = plt.subplots(figsize=(8, 4))
    hourly = df.groupby('Hora')['kW_Instant'].mean()
    hourly_all = pd.Series(0.0, index=range(24))
    for h in hourly.index:
        hourly_all[h] = hourly[h]
    mean_val = hourly_all[hourly_all > 0].mean() if (hourly_all > 0).any() else 0
    colors = []
    for v in hourly_all.values:
        if v > mean_val * 1.15:
            colors.append('#E74C3C')
        elif v > mean_val * 0.85:
            colors.append('#F39C12')
        else:
            colors.append('#00B4D8')
    bars = ax.bar(hourly_all.index, hourly_all.values, color=colors, edgecolor='white', linewidth=0.8)
    ax.axhline(mean_val, color='#2ECC71', linestyle='--', linewidth=2)
    for bar, val in zip(bars, hourly_all.values):
        if val > 0:
            ax.annotate(f'{val:.1f}', xy=(bar.get_x() + bar.get_width() / 2, val),
                       xytext=(0, 3), textcoords='offset points',
                       ha='center', va='bottom', fontsize=7, fontweight='bold')
    ax.set_title(title, fontsize=13, fontweight='bold', pad=12)
    ax.set_ylabel('Avg Power (kW)', fontsize=10)
    ax.set_xlabel('Hour of Day', fontsize=10)
    ax.set_xticks(range(24))
    ax.grid(True, linestyle='--', alpha=0.3)
    from matplotlib.patches import Patch
    legend_els = [Patch(facecolor='#E74C3C', label='High (>115% avg)'),
                  Patch(facecolor='#F39C12', label='Normal (85-115%)'),
                  Patch(facecolor='#00B4D8', label='Low (<85% avg)'),
                  Patch(facecolor='#2ECC71', label='Daily mean')]
    ax.legend(handles=legend_els, fontsize=8, loc='upper right')
    fig.patch.set_facecolor('white')
    ax.set_facecolor('#F8F9FA')
    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf

def create_peaks_scatter_png(df, time_col, peaks_df, threshold, title):
    """Grafico de picos con labels de valor kW y timestamp en cada evento"""
    fig, ax = plt.subplots(figsize=(8, 4))
    n = max(1, len(df) // 500)
    df_plot = df.iloc[::n]
    ax.plot(range(len(df_plot)), df_plot['kW_Instant'].values,
            color='#00B4D8', linewidth=1, alpha=0.7, label='Power (kW)')
    ax.axhline(threshold, color='orange', linestyle='--', linewidth=1.5,
               label=f'Threshold: {threshold:.2f} kW')
    if not peaks_df.empty:
        top_peaks = peaks_df.nlargest(min(15, len(peaks_df)), 'kW_Instant')
        for _, row in top_peaks.iterrows():
            try:
                ts = row[time_col]
                closest_idx = (df[time_col] - ts).abs().idxmin()
                x_pos = closest_idx // n
                ax.scatter(x_pos, row['kW_Instant'], color='red', s=80, zorder=5, edgecolors='white')
                ax.annotate(
                    f"{row['kW_Instant']:.1f}kW\n{ts.strftime('%m/%d %H:%M')}",
                    xy=(x_pos, row['kW_Instant']),
                    xytext=(8, 5), textcoords='offset points',
                    fontsize=6.5, color='#C0392B', fontweight='bold',
                    arrowprops=dict(arrowstyle='->', color='#C0392B', lw=0.8)
                )
            except Exception:
                pass
    ax.set_title(title, fontsize=13, fontweight='bold', pad=12)
    ax.set_ylabel('Power (kW)', fontsize=10)
    ax.set_xlabel('Time (sampled)', fontsize=10)
    ax.legend(fontsize=9)
    ax.grid(True, linestyle='--', alpha=0.3)
    fig.patch.set_facecolor('white')
    ax.set_facecolor('#F8F9FA')
    plt.tight_layout()
    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=150, bbox_inches='tight')
    buf.seek(0)
    plt.close(fig)
    return buf

def calculate_technical_kpis(df, time_col, energia_total):
    """Calcula KPIs tecnicos de ingenieria electrica"""
    avg_kw = df['kW_Instant'].mean()
    max_kw = df['kW_Instant'].max()
    min_kw = df['kW_Instant'].min()
    std_kw = df['kW_Instant'].std()
    horas  = (df[time_col].max() - df[time_col].min()).total_seconds() / 3600.0

    demand_factor    = avg_kw / max_kw if max_kw > 0 else 0.0
    load_factor      = energia_total / (max_kw * horas) if (max_kw * horas) > 0 else 0.0
    par              = max_kw / avg_kw if avg_kw > 0 else 0.0
    cov              = (std_kw / avg_kw * 100.0) if avg_kw > 0 else 0.0
    energy_intensity = energia_total / horas if horas > 0 else 0.0

    if load_factor >= 0.80:
        efficiency_class = "EXCELLENT  (>80%)"
    elif load_factor >= 0.60:
        efficiency_class = "GOOD       (60-80%)"
    elif load_factor >= 0.40:
        efficiency_class = "FAIR       (40-60%)"
    else:
        efficiency_class = "POOR       (<40%)"

    if cov < 15:
        stability = "STABLE     (CoV <15%)"
    elif cov < 30:
        stability = "MODERATE   (CoV 15-30%)"
    else:
        stability = "UNSTABLE   (CoV >30%)"

    recommendations = []
    if load_factor < 0.50:
        recommendations.append("Low load factor: consider consolidating shifts or rescheduling heavy loads to fill gaps.")
    if cov > 30:
        recommendations.append("High variability: investigate irregular demand spikes and process inconsistencies.")
    if par > 2.5:
        recommendations.append("High PAR: peak shaving strategies (capacitor banks, demand limiters) recommended.")
    if demand_factor < 0.50:
        recommendations.append("Low demand factor: installed capacity may be oversized relative to actual usage.")
    if not recommendations:
        recommendations.append("Operating within efficient parameters. Continue periodic monitoring.")

    return {
        'avg_kw': avg_kw, 'max_kw': max_kw, 'min_kw': min_kw, 'std_kw': std_kw,
        'horas': horas, 'demand_factor': demand_factor, 'load_factor': load_factor,
        'par': par, 'cov': cov, 'energy_intensity': energy_intensity,
        'efficiency_class': efficiency_class, 'stability': stability,
        'energia_total': energia_total, 'recommendations': recommendations
    }

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
            amp_col  = df.columns[2] if len(df.columns) > 2 else df.columns[1]
            df[time_col] = pd.to_datetime(df[time_col], errors='coerce')
            df[amp_col]  = pd.to_numeric(df[amp_col], errors='coerce')
            df = df.dropna(subset=[time_col]).reset_index(drop=True)
            df.rename(columns={time_col: 'DateTime', amp_col: 'Amperios'}, inplace=True)
            return df, 'DateTime', 'Amperios'
    except Exception as e:
        raise RuntimeError(f"Error procesando archivo: {str(e)}")

@st.cache_data(show_spinner="Calculando metricas...")
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
            mode='markers+text',
            name='⚠️ Peak Event',
            text=[f"{v:.1f} kW" for v in peaks['kW_Instant']],
            textposition='top center',
            textfont=dict(size=10, color='#FF4444'),
            marker=dict(color='red', size=12, symbol='circle', line=dict(color='white', width=2)),
            hovertemplate='<b>Peak</b>: %{y:.2f} kW<br><b>Time</b>: %{x|%Y-%m-%d %H:%M}<extra></extra>'
        ))
    fig.update_layout(template="plotly_dark", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)

    if not peaks.empty:
        st.markdown("#### 🔴 Top 10 Peak Events")
        top10 = peaks.nlargest(10, 'kW_Instant')[[time_col, 'kW_Instant', 'Turno', 'peak_magnitude']].copy()
        top10.columns = ['Timestamp', 'Power (kW)', 'Shift', 'Over Threshold (kW)']
        top10['Power (kW)'] = top10['Power (kW)'].round(3)
        top10['Over Threshold (kW)'] = top10['Over Threshold (kW)'].round(3)
        st.dataframe(top10, use_container_width=True, hide_index=True)

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

# --- PDF TECNICO DIARIO ---

def render_pdf_daily(df_filt, t_col, energia_total, machine_name):
    """PDF Diario Tecnico: KPIs de ingenieria, 6 graficas, tabla de picos, recomendaciones"""
    if not PDF_ENABLED:
        st.warning("PDF generation requires fpdf and matplotlib")
        return
    if st.button("📑 Generate Technical Daily Report", use_container_width=True, key="pdf_daily_btn"):
        with st.spinner("Generating technical report..."):
            try:
                kpis         = calculate_technical_kpis(df_filt, t_col, energia_total)
                fecha_inicio = df_filt[t_col].min().strftime('%B %d, %Y')
                fecha_fin    = df_filt[t_col].max().strftime('%B %d, %Y')
                costo_total  = energia_total * COSTO_KWH

                series_img = create_technical_series_png(df_filt, t_col,
                    'Power Time Series with Mean, +-1sigma and P95')

                peaks, threshold = detect_peaks_vectorized(df_filt, 'kW_Instant', 95)
                peaks_img  = create_peaks_scatter_png(df_filt, t_col, peaks, threshold,
                    'Peak Demand Events (P95 threshold) - Labeled')

                hourly_img = create_hourly_avg_png(df_filt,
                    'Average Power by Hour of Day (color-coded by level)')

                shift_data     = df_filt.groupby('Turno')['kW_Instant'].mean().to_dict()
                shift_data_fmt = {f"Shift {k}": v for k, v in shift_data.items()}
                bar_img        = create_bar_chart_png(shift_data_fmt,
                    'Average Power per Shift', 'Shift', 'Power (kW)')

                shift_energy   = df_filt.groupby('Turno')['kW_Instant'].sum().to_dict()
                shift_e_fmt    = {f"Shift {k}": v for k, v in shift_energy.items()}
                pie_img        = create_pie_chart_png(shift_e_fmt, 'Energy Share by Shift (%)')

                daily_data = df_filt.groupby('Dia')['kW_Instant'].mean().to_dict() if 'Dia' in df_filt.columns else df_filt.groupby('Día')['kW_Instant'].mean().to_dict()
                daily_fmt  = {str(k)[-5:]: v for k, v in list(daily_data.items())[-14:]}
                trend_img  = create_line_chart_png(daily_fmt,
                    'Daily Average Power Trend', 'Date', 'Power (kW)')

                pdf = ExecutivePDF()

                # PAGINA 1: KPIs tecnicos
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 14)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 10, f"Technical Daily Report - {machine_name}", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(60, 60, 60)
                pdf.multi_cell(0, 6, sanitize_pdf(
                    f"Machine: {machine_name}  |  Period: {fecha_inicio} to {fecha_fin}  |  "
                    f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                ))
                pdf.ln(5)

                pdf.set_font('Helvetica', 'B', 12)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 8, "1. Electrical Engineering KPIs", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(30, 30, 30)

                kpi_rows = [
                    ("Monitoring Period",            f"{kpis['horas']:.2f} hours"),
                    ("Total Records Analyzed",       f"{len(df_filt):,}"),
                    ("Total Energy Consumed",        f"{energia_total:,.4f} kWh"),
                    ("Average Power",                f"{kpis['avg_kw']:.4f} kW"),
                    ("Maximum Peak Power",           f"{kpis['max_kw']:.4f} kW"),
                    ("Minimum Power Recorded",       f"{kpis['min_kw']:.4f} kW"),
                    ("Standard Deviation (sigma)",   f"{kpis['std_kw']:.4f} kW"),
                    ("Demand Factor  (Avg/Peak)",    f"{kpis['demand_factor']:.4f}   ({kpis['demand_factor']*100:.2f}%)"),
                    ("Load Factor    (E / E_max)",   f"{kpis['load_factor']:.4f}   ({kpis['load_factor']*100:.2f}%)"),
                    ("Peak-to-Avg Ratio (PAR)",      f"{kpis['par']:.4f}"),
                    ("Coeff. of Variation (CoV)",    f"{kpis['cov']:.2f}%"),
                    ("Energy Intensity",             f"{kpis['energy_intensity']:.4f} kW/h"),
                    ("Efficiency Classification",   sanitize_pdf(kpis['efficiency_class'])),
                    ("Demand Stability",             sanitize_pdf(kpis['stability'])),
                    ("Estimated Energy Cost",        f"${costo_total:,.2f} MXN  (@  ${COSTO_KWH} MXN/kWh)"),
                    ("Peak Events (P95)",            f"{len(peaks)} events above {threshold:.3f} kW"),
                ]
                for i, (label, value) in enumerate(kpi_rows):
                    pdf.set_font('Helvetica', 'B', 9)
                    fill = i % 2 == 0
                    pdf.set_fill_color(235, 248, 252) if fill else pdf.set_fill_color(255, 255, 255)
                    pdf.cell(80, 7, sanitize_pdf(label), border=1, fill=fill)
                    pdf.set_font('Helvetica', '', 9)
                    pdf.cell(0, 7, sanitize_pdf(value), border=1, fill=fill, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(5)

                # Shift efficiency table
                pdf.set_font('Helvetica', 'B', 12)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 8, "2. Shift Efficiency Analysis", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(30, 30, 30)
                pdf.set_font('Helvetica', 'B', 9)
                pdf.set_fill_color(0, 180, 216)
                pdf.set_text_color(255, 255, 255)
                hdrs = ["Shift", "Avg kW", "Max kW", "Min kW", "Std kW", "CoV%", "% Energy"]
                ws   = [28, 27, 27, 27, 27, 22, 32]
                for hdr, w in zip(hdrs, ws):
                    pdf.cell(w, 7, hdr, border=1, fill=True, align='C')
                pdf.ln()
                pdf.set_text_color(30, 30, 30)
                total_e = df_filt['kW_Instant'].sum()
                for idx, shift_num in enumerate(sorted(df_filt['Turno'].unique())):
                    sub = df_filt[df_filt['Turno'] == shift_num]
                    pct = sub['kW_Instant'].sum() / total_e * 100 if total_e > 0 else 0
                    cov_s = sub['kW_Instant'].std() / sub['kW_Instant'].mean() * 100 if sub['kW_Instant'].mean() > 0 else 0
                    row_vals = [
                        f"Shift {shift_num}",
                        f"{sub['kW_Instant'].mean():.3f}",
                        f"{sub['kW_Instant'].max():.3f}",
                        f"{sub['kW_Instant'].min():.3f}",
                        f"{sub['kW_Instant'].std():.3f}",
                        f"{cov_s:.1f}%",
                        f"{pct:.1f}%"
                    ]
                    pdf.set_font('Helvetica', '', 9)
                    fill = idx % 2 == 0
                    pdf.set_fill_color(245, 250, 255) if fill else pdf.set_fill_color(255, 255, 255)
                    for v, w in zip(row_vals, ws):
                        pdf.cell(w, 7, v, border=1, fill=fill, align='C')
                    pdf.ln()
                pdf.ln(5)

                pdf.set_font('Helvetica', 'B', 12)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 8, "3. Technical Recommendations", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(30, 30, 30)
                pdf.set_font('Helvetica', '', 10)
                for rec in kpis['recommendations']:
                    pdf.cell(6, 6, '*')
                    pdf.multi_cell(0, 6, sanitize_pdf(rec))
                    pdf.ln(1)

                # PAGINA 2: Serie de tiempo
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 12)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 8, "4. Power Time Series - Statistical Bands", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', '', 8)
                pdf.set_text_color(80, 80, 80)
                pdf.multi_cell(0, 5, sanitize_pdf(
                    f"Blue: instantaneous power  |  Green dashed: mean ({kpis['avg_kw']:.2f} kW)  |  "
                    f"Orange dotted: +1 sigma  |  Red dashed: P95 ({np.percentile(df_filt['kW_Instant'], 95):.2f} kW)"
                ))
                pdf.ln(2)
                pdf.image(series_img, x=10, w=190)

                # PAGINA 3: Picos con labels
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 12)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 8, "5. Peak Demand Events - Labeled (P95)", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', '', 8)
                pdf.set_text_color(80, 80, 80)
                pdf.multi_cell(0, 5, sanitize_pdf(
                    f"Threshold (P95): {threshold:.3f} kW  |  "
                    f"Total events: {len(peaks)}  |  "
                    f"Max recorded: {kpis['max_kw']:.3f} kW  |  "
                    f"PAR: {kpis['par']:.3f}"
                ))
                pdf.ln(2)
                pdf.image(peaks_img, x=10, w=190)

                if not peaks.empty:
                    pdf.ln(3)
                    pdf.set_font('Helvetica', 'B', 10)
                    pdf.set_text_color(0, 180, 216)
                    pdf.cell(0, 7, "Top 15 Peak Events - Detail Table", new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font('Helvetica', 'B', 8)
                    pdf.set_fill_color(0, 180, 216)
                    pdf.set_text_color(255, 255, 255)
                    p_hdrs = ["Timestamp", "Power (kW)", "Shift", "Over Threshold (kW)", "Hour"]
                    p_ws   = [58, 35, 22, 50, 25]
                    for hdr, w in zip(p_hdrs, p_ws):
                        pdf.cell(w, 7, hdr, border=1, fill=True, align='C')
                    pdf.ln()
                    top15 = peaks.nlargest(15, 'kW_Instant')
                    pdf.set_text_color(30, 30, 30)
                    for i, (_, row) in enumerate(top15.iterrows()):
                        pdf.set_font('Helvetica', '', 8)
                        fill = i % 2 == 0
                        pdf.set_fill_color(250, 245, 245) if fill else pdf.set_fill_color(255, 255, 255)
                        mag = row.get('peak_magnitude', row['kW_Instant'] - threshold)
                        row_data = [
                            row[t_col].strftime('%Y-%m-%d %H:%M:%S'),
                            f"{row['kW_Instant']:.4f}",
                            f"Shift {int(row['Turno'])}",
                            f"+{mag:.4f}",
                            f"{int(row['Hora'])}:00"
                        ]
                        for v, w in zip(row_data, p_ws):
                            pdf.cell(w, 6, v, border=1, fill=fill, align='C')
                        pdf.ln()

                # PAGINA 4: Distribucion horaria
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 12)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 8, "6. Hourly Power Distribution (0-23h)", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', '', 8)
                pdf.set_text_color(80, 80, 80)
                pdf.multi_cell(0, 5, sanitize_pdf(
                    "Red: >115% of daily mean  |  Orange: 85-115%  |  Blue: <85%  |  "
                    "Shift 1: 06-14h  |  Shift 2: 14-22h  |  Shift 3: 22-06h"
                ))
                pdf.ln(2)
                pdf.image(hourly_img, x=10, w=190)

                # PAGINA 5: Comparativa por turno
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 12)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 8, "7. Shift Comparison - Power and Energy Share", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)
                y_cur = pdf.get_y()
                pdf.image(bar_img, x=10, y=y_cur, w=93)
                pdf.image(pie_img, x=107, y=y_cur, w=93)
                pdf.ln(80)

                # PAGINA 6: Tendencia diaria
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 12)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 8, "8. Daily Average Power Trend", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', '', 8)
                pdf.set_text_color(80, 80, 80)
                pdf.multi_cell(0, 5, sanitize_pdf("Red dots = days exceeding 120% of period average."))
                pdf.ln(2)
                pdf.image(trend_img, x=10, w=190)

                pdf_bytes = bytes(pdf.output())
                st.success("✅ Technical daily report generated!")
                st.download_button(
                    label="📥 Download Technical Daily PDF",
                    data=pdf_bytes,
                    file_name=f"Technical_Daily_{machine_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"Error generating PDF: {str(e)}")
                st.code(traceback.format_exc())

# --- PDF TECNICO MENSUAL ---

def render_pdf_monthly(df_cloud, machine_name):
    """PDF Mensual Tecnico con estadisticas, comparativa avg vs pico, tabla dia a dia"""
    if not PDF_ENABLED:
        st.warning("PDF generation requires fpdf and matplotlib")
        return
    if df_cloud.empty:
        st.warning("No monthly data available. Use Cloud Sync to upload data first.")
        return

    if st.button("📑 Generate Technical Monthly Report", use_container_width=True, key="pdf_monthly_btn"):
        with st.spinner("Generating technical monthly report..."):
            try:
                energia_mensual = (df_cloud['Potencia_Promedio_kW'] * 24).sum()
                costo_total     = energia_mensual * COSTO_KWH
                avg_p  = df_cloud['Potencia_Promedio_kW'].mean()
                max_p  = df_cloud['Pico_Maximo_kW'].max()
                min_p  = df_cloud['Potencia_Promedio_kW'].min()
                std_p  = df_cloud['Potencia_Promedio_kW'].std()
                load_f = avg_p / max_p if max_p > 0 else 0
                cov    = (std_p / avg_p * 100) if avg_p > 0 else 0
                fecha_inicio = df_cloud['Día'].min().strftime('%B %d, %Y')
                fecha_fin    = df_cloud['Día'].max().strftime('%B %d, %Y')

                daily_data  = df_cloud.set_index('Día')['Potencia_Promedio_kW'].to_dict()
                daily_fmt   = {k.strftime('%m/%d'): v for k, v in list(daily_data.items())[-20:]}
                avg_img     = create_line_chart_png(daily_fmt, 'Daily Average Power Trend', 'Date', 'Avg kW')

                peak_data   = df_cloud.set_index('Día')['Pico_Maximo_kW'].to_dict()
                peak_fmt    = {k.strftime('%m/%d'): v for k, v in list(peak_data.items())[-20:]}
                peak_img    = create_line_chart_png(peak_fmt, 'Daily Peak Demand', 'Date', 'Peak kW')

                fig_c, ax_c = plt.subplots(figsize=(8, 4))
                x_c = range(len(df_cloud))
                ax_c.bar(x_c, df_cloud['Pico_Maximo_kW'].values, label='Peak kW', color='#FF6B6B', alpha=0.7)
                ax_c.bar(x_c, df_cloud['Potencia_Promedio_kW'].values, label='Avg kW', color='#00B4D8', alpha=0.9)
                ax_c.axhline(avg_p, color='#2ECC71', linestyle='--', linewidth=2, label=f'Monthly Avg: {avg_p:.2f} kW')
                for i, (_, row) in enumerate(df_cloud.iterrows()):
                    ax_c.annotate(f"{row['Pico_Maximo_kW']:.1f}",
                                  xy=(i, row['Pico_Maximo_kW']),
                                  xytext=(0, 3), textcoords='offset points',
                                  ha='center', va='bottom', fontsize=5.5, color='#C0392B')
                ax_c.set_title('Daily Average vs Peak Power', fontsize=13, fontweight='bold', pad=12)
                ax_c.set_ylabel('Power (kW)', fontsize=10)
                ax_c.set_xlabel(f'Day (n={len(df_cloud)})', fontsize=10)
                ax_c.legend(fontsize=9)
                ax_c.grid(True, linestyle='--', alpha=0.3)
                fig_c.patch.set_facecolor('white')
                ax_c.set_facecolor('#F8F9FA')
                plt.tight_layout()
                buf_cmp = BytesIO()
                fig_c.savefig(buf_cmp, format='png', dpi=150, bbox_inches='tight')
                buf_cmp.seek(0)
                plt.close(fig_c)

                pdf = ExecutivePDF()

                # PAGINA 1: KPIs mensuales
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 14)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 10, f"Technical Monthly Report - {machine_name}", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', '', 10)
                pdf.set_text_color(60, 60, 60)
                pdf.multi_cell(0, 6, sanitize_pdf(
                    f"Machine: {machine_name}  |  Period: {fecha_inicio} to {fecha_fin}  |  "
                    f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
                ))
                pdf.ln(5)

                pdf.set_font('Helvetica', 'B', 12)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 8, "1. Monthly Electrical KPIs", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(30, 30, 30)
                kpi_rows = [
                    ("Total Days Analyzed",             f"{len(df_cloud)} days"),
                    ("Analysis Period",                  f"{fecha_inicio} to {fecha_fin}"),
                    ("Total Estimated Energy",           f"{energia_mensual:,.3f} kWh"),
                    ("Monthly Average Power",            f"{avg_p:.4f} kW"),
                    ("Maximum Daily Peak",               f"{max_p:.4f} kW"),
                    ("Minimum Daily Avg Power",          f"{min_p:.4f} kW"),
                    ("Std Deviation (daily avg)",        f"{std_p:.4f} kW"),
                    ("Coefficient of Variation (CoV)",  f"{cov:.2f}%"),
                    ("Load Factor (avg / peak)",         f"{load_f:.4f}   ({load_f*100:.2f}%)"),
                    ("Peak Day",                         df_cloud.loc[df_cloud['Pico_Maximo_kW'].idxmax(), 'Día'].strftime('%Y-%m-%d')),
                    ("Highest Avg Day",                  df_cloud.loc[df_cloud['Potencia_Promedio_kW'].idxmax(), 'Día'].strftime('%Y-%m-%d')),
                    ("Lowest Avg Day",                   df_cloud.loc[df_cloud['Potencia_Promedio_kW'].idxmin(), 'Día'].strftime('%Y-%m-%d')),
                    ("Estimated Energy Cost",            f"${costo_total:,.2f} MXN  (@  ${COSTO_KWH} MXN/kWh)"),
                ]
                for i, (label, value) in enumerate(kpi_rows):
                    pdf.set_font('Helvetica', 'B', 9)
                    fill = i % 2 == 0
                    pdf.set_fill_color(235, 248, 252) if fill else pdf.set_fill_color(255, 255, 255)
                    pdf.cell(85, 7, sanitize_pdf(label), border=1, fill=fill)
                    pdf.set_font('Helvetica', '', 9)
                    pdf.cell(0, 7, sanitize_pdf(str(value)), border=1, fill=fill, new_x="LMARGIN", new_y="NEXT")
                pdf.ln(5)

                # PAGINA 2: Tabla dia a dia
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 12)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 8, "2. Day-by-Day Technical Detail", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(30, 30, 30)
                pdf.set_font('Helvetica', 'B', 8)
                pdf.set_fill_color(0, 180, 216)
                pdf.set_text_color(255, 255, 255)
                t_hdrs = ["#", "Date", "Avg Power (kW)", "Peak Power (kW)", "Est. kWh", "Peak/Avg"]
                t_ws   = [15, 38, 38, 38, 32, 29]
                for hdr, w in zip(t_hdrs, t_ws):
                    pdf.cell(w, 7, hdr, border=1, fill=True, align='C')
                pdf.ln()
                pdf.set_text_color(30, 30, 30)
                for i, (_, row) in enumerate(df_cloud.iterrows()):
                    pdf.set_font('Helvetica', '', 8)
                    fill = i % 2 == 0
                    pdf.set_fill_color(245, 250, 255) if fill else pdf.set_fill_color(255, 255, 255)
                    kwh_est = row['Potencia_Promedio_kW'] * 24
                    ratio   = row['Pico_Maximo_kW'] / row['Potencia_Promedio_kW'] if row['Potencia_Promedio_kW'] > 0 else 0
                    vals = [
                        str(i + 1),
                        row['Día'].strftime('%Y-%m-%d'),
                        f"{row['Potencia_Promedio_kW']:.4f}",
                        f"{row['Pico_Maximo_kW']:.4f}",
                        f"{kwh_est:.2f}",
                        f"{ratio:.3f}"
                    ]
                    for v, w in zip(vals, t_ws):
                        pdf.cell(w, 6, v, border=1, fill=fill, align='C')
                    pdf.ln()
                    if pdf.get_y() > 265:
                        pdf.add_page()
                        pdf.set_font('Helvetica', 'B', 8)
                        pdf.set_fill_color(0, 180, 216)
                        pdf.set_text_color(255, 255, 255)
                        for hdr, w in zip(t_hdrs, t_ws):
                            pdf.cell(w, 7, hdr, border=1, fill=True, align='C')
                        pdf.ln()
                        pdf.set_text_color(30, 30, 30)

                # Paginas de graficas
                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 12)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 8, "3. Daily Average Power Trend", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', '', 8)
                pdf.set_text_color(80, 80, 80)
                pdf.multi_cell(0, 5, sanitize_pdf("Red dots = days exceeding 120% of period average."))
                pdf.ln(2)
                pdf.image(avg_img, x=10, w=190)

                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 12)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 8, "4. Daily Peak Demand", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)
                pdf.image(peak_img, x=10, w=190)

                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 12)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 8, "5. Daily Average vs Peak Comparison (labeled)", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', '', 8)
                pdf.set_text_color(80, 80, 80)
                pdf.multi_cell(0, 5, sanitize_pdf(
                    f"Red: daily peak  |  Blue: daily average  |  "
                    f"Green dashed: monthly avg ({avg_p:.2f} kW)  |  Labels = peak kW per day"
                ))
                pdf.ln(2)
                pdf.image(buf_cmp, x=10, w=190)

                pdf_bytes = bytes(pdf.output())
                st.success("✅ Technical monthly report generated!")
                st.download_button(
                    label="📥 Download Technical Monthly PDF",
                    data=pdf_bytes,
                    file_name=f"Technical_Monthly_{machine_name}_{datetime.now().strftime('%Y%m')}.pdf",
                    mime="application/pdf"
                )
            except Exception as e:
                st.error(f"Error generating PDF: {str(e)}")
                st.code(traceback.format_exc())

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
    """Renderiza el selector de maquinas en el sidebar"""
    st.sidebar.markdown("### 🏭 Machine Management")

    machines_df = get_machines()

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

    if not machines_df.empty:
        machine_options = {row['machine_name']: row['id'] for _, row in machines_df.iterrows()}
        selected_machine_name = st.sidebar.selectbox(
            "Select Machine",
            options=list(machine_options.keys()),
            key="machine_selector"
        )
        selected_machine_id = machine_options[selected_machine_name]

        machine_info = machines_df[machines_df['id'] == selected_machine_id].iloc[0]
        if machine_info.get('description'):
            st.sidebar.caption(f"📝 {machine_info['description']}")

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

machine_id, machine_name = render_machine_selector()

if not machine_id:
    st.markdown("""<div style="text-align: center; padding: 50px; background-color: #1a1e23; border-radius: 15px;">
            <h1 style="color: #4a4e53; font-size: 60px;">🏭</h1>
            <h2 style="color: #e0e6ed;">No Machine Selected</h2>
            <p style="color: #9aa0a6;">Create a machine in the sidebar to start analyzing data.</p>
            </div>""", unsafe_allow_html=True)
else:
    with st.sidebar:
        st.markdown(f"### 📡 Upload Data - {machine_name}")
        uploaded_file = st.file_uploader(
            f"Upload HOBO Report for {machine_name} (CSV/XLSX)",
            type=["csv", "xlsx"],
            key=f"upload_{machine_id}"
        )
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
            pf   = st.number_input("Power Factor (PF):", 0.5, 1.0, 0.9, 0.01)
            st.info(f"💵 kWh Price: ${COSTO_KWH} MXN (fixed)")
        with st.expander("🎯 Filter Engine", expanded=True):
            peak_sens = st.slider("Peak Sensitivity (%):", 80, 99, 95, 1)

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

            min_d, max_d = get_filter_bounds(df_proc, t_col)
            with st.sidebar:
                with st.expander("🎯 Filter Engine", expanded=True):
                    range_d = st.date_input(
                        "Time Range:", [min_d.date(), max_d.date()], key="date_range"
                    )
                    shifts = st.multiselect("Shifts:", [1, 2, 3], default=[1, 2, 3], key="shifts")

                    # FILTRO POR POTENCIA kW
                    kw_min_val = float(df_proc['kW_Instant'].min())
                    kw_max_val = float(df_proc['kW_Instant'].max())
                    if kw_max_val > kw_min_val:
                        kw_step = round(max(0.001, (kw_max_val - kw_min_val) / 200), 3)
                        kw_range = st.slider(
                            "⚡ Power Filter (kW):",
                            min_value=kw_min_val,
                            max_value=kw_max_val,
                            value=(kw_min_val, kw_max_val),
                            step=kw_step,
                            key="kw_range",
                            format="%.2f",
                            help="Filter records by instantaneous power range"
                        )
                    else:
                        kw_range = (kw_min_val, kw_max_val)
                        st.info(f"Power: {kw_min_val:.2f} kW (constant)")

            # Aplicar filtros acumulados
            df_filt = df_proc[df_proc['Turno'].isin(shifts)].copy()
            if len(range_d) == 2:
                df_filt = df_filt[
                    (df_filt['Día'] >= range_d[0]) & (df_filt['Día'] <= range_d[1])
                ]
            df_filt = df_filt[
                (df_filt['kW_Instant'] >= kw_range[0]) &
                (df_filt['kW_Instant'] <= kw_range[1])
            ].copy()

            if df_filt.empty:
                st.warning("⚠️ No data found with selected filters.")
            else:
                e_total = calculate_energy_vectorized(df_filt, t_col, 'kW_Instant')

                # ACCIONES RAPIDAS EN SIDEBAR
                with st.sidebar:
                    st.markdown("---")
                    st.markdown("### 💾 Quick Actions")

                    excel_buffer = io.BytesIO()
                    df_export = df_filt[[t_col, a_col, 'kW_Instant', 'Turno', 'Hora', 'Día']].copy()
                    df_export.columns = ['DateTime', 'Amps', 'kW_Instant', 'Shift', 'Hour', 'Day']
                    daily_summary = df_filt.groupby('Día').agg(
                        Avg_kW=('kW_Instant', 'mean'),
                        Peak_kW=('kW_Instant', 'max'),
                        Min_kW=('kW_Instant', 'min'),
                        Std_kW=('kW_Instant', 'std'),
                        Records=('kW_Instant', 'count')
                    ).reset_index()
                    with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                        df_export.to_excel(writer, sheet_name='ProcessedData', index=False)
                        daily_summary.to_excel(writer, sheet_name='DailySummary', index=False)
                    st.download_button(
                        label="📊 Download Excel",
                        data=excel_buffer.getvalue(),
                        file_name=f"Data_{machine_name}_{datetime.now().strftime('%Y%m%d_%H%M')}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                        key="excel_dl"
                    )

                    if supabase_client:
                        if st.button("☁️ Save to Cloud", use_container_width=True,
                                     key="quick_save_cloud", type="primary"):
                            with st.spinner("Saving..."):
                                daily_save = df_filt.groupby('Día').agg(
                                    Potencia_Promedio_kW=('kW_Instant', 'mean'),
                                    Pico_Maximo_kW=('kW_Instant', 'max')
                                ).reset_index()
                                if save_machine_data(machine_id, daily_save):
                                    st.success(f"✅ {machine_name} saved!")
                                else:
                                    st.error("Save failed")

                    st.markdown("---")
                    st.caption(f"**Filtered:** {len(df_filt):,} records")
                    st.caption(f"**Avg:** {df_filt['kW_Instant'].mean():.2f} kW")
                    st.caption(f"**Peak:** {df_filt['kW_Instant'].max():.2f} kW")
                    st.caption(f"**Energy:** {e_total:.1f} kWh")
                    st.caption(f"**Est. cost:** ${e_total * COSTO_KWH:,.0f} MXN")

                historical_data = load_machine_data(machine_id)

                if selected_page == "KPI Dashboard":
                    render_kpi_dashboard(df_filt, t_col, a_col, e_total, machine_name)
                elif selected_page == "Trends & Peaks":
                    render_tendencias_picos(df_filt, t_col, a_col, peak_sens)
                elif selected_page == "Behaviors":
                    render_analisis_turnos(df_filt, volt)
                elif selected_page == "Monthly Insights":
                    render_monthly_insights(historical_data, machine_name)
                elif selected_page == "Executive PDF":
                    st.markdown(
                        f"<h2 align='center' style='color:#00FFAA;'>📄 Technical Executive PDF Reports - {machine_name}</h2>",
                        unsafe_allow_html=True
                    )
                    tab_daily, tab_monthly = st.tabs(["📅 Daily Technical Report", "📆 Monthly Technical Report"])
                    with tab_daily:
                        render_pdf_daily(df_filt, t_col, e_total, machine_name)
                    with tab_monthly:
                        render_pdf_monthly(historical_data, machine_name)
                elif selected_page == "Cloud Sync":
                    render_cloud_sync(df_filt, machine_id, machine_name)

        except Exception as e:
            st.error(f"⚠️ Error: {str(e)}")
            st.code(traceback.format_exc())

st.markdown("<p style='text-align: right; color:#555; font-size:12px;'>Vector-Core Engine v6.1 | Multi-Machine | Rate: $2.40/kWh</p>", unsafe_allow_html=True)
