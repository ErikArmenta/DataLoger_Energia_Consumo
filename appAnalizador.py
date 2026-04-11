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

# Configuración inicial
st.set_page_config(page_title="EA Energy Analyzer", layout="wide", page_icon="⚡")

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
    """Helper para crear gráficas profesionales con etiquetas para el PDF usando Matplotlib"""
    fig, ax = plt.subplots(figsize=(10, 5))
    
    if chart_type == 'bar':
        colors = ['#00B4D8', '#FF6B6B', '#4ECDC4']
        bars = ax.bar(df[x_col].astype(str), df[y_col], color=colors[:len(df)])
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        # Añadir etiquetas sobre las barras
        for bar in bars:
            height = bar.get_height()
            ax.annotate(f'{height:.2f}',
                        xy=(bar.get_x() + bar.get_width() / 2, height),
                        xytext=(0, 3),  # 3 points vertical offset
                        textcoords="offset points",
                        ha='center', va='bottom', fontsize=9, fontweight='bold')
    
    elif chart_type == 'line':
        ax.plot(df[x_col], df[y_col], color='#00B4D8', marker='o', markersize=4, linewidth=2, label='Energy Trend')
        ax.set_title(title, fontsize=14, fontweight='bold', pad=15)
        
        if highlight_peaks:
            # Identificar picos altos (ej: top 10% o por encima de la media)
            threshold = df[y_col].mean() * 1.2
            peaks = df[df[y_col] > threshold]
            
            # Dibujar puntos rojos en los picos
            ax.scatter(peaks[x_col], peaks[y_col], color='red', s=60, edgecolors='white', zorder=5, label='High Peaks')
            
            # Añadir etiquetas solo a los picos
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
    
    # Ajustar estética
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
    """Elimina caracteres Unicode fuera del rango Latin-1 para compatibilidad con Helvetica en fpdf2"""
    replacements = {
        '\u2014': ' - ', '\u2013': ' - ', '\u2022': '*', '\u2019': "'",
        '\u201c': '"', '\u201d': '"', '\u2018': "'", '\u2026': '...',
        '\u00e9': 'e', '\u00ed': 'i', '\u00f3': 'o', '\u00fa': 'u', '\u00e1': 'a',
    }
    for uni, asc in replacements.items():
        text = text.replace(uni, asc)
    # Descarte final: cualquier caracter fuera de Latin-1
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
        st.info(
            f"**🎯 Instant Diagnostics**\n"
            f"- **Most Critical Shift:** Shift {worst_shift} - highest average load\n"
            f"- **Most Efficient Shift:** Shift {best_shift} - lowest average load"
        )
    with col_b:
        st.metric("📉 Consumption Variability", f"{variability:.2%}",
                  help="Coefficient of Variation. High values indicate unstable demand.")
        st.metric("💵 Estimated Cost", f"${costo_total:,.2f} MXN",
                  help=f"Based on ${costo_kwh:.2f} MXN/kWh tariff")
    with col_c:
        # Construir lista de horas pico como string único para evitar layouts inestables
        peak_list = "\n".join([f"- **{int(hr):02d}:00** &rarr; {val:.1f} kW" for hr, val in peak_hours.items()])
        st.markdown(
            f"**⏰ Peak Demand Hours:**\n{peak_list}\n\n"
            f"**🔋 Total Energy:** {energia_total:.2f} kWh"
        )

@st.fragment
def render_tendencias_picos(df_filtered, time_col, amp_col, peak_percentile):
    st.markdown("<h2 align='center' style='color:#FF6B6B;'>📈 Time Trend & Peak Analysis</h2>", unsafe_allow_html=True)
    peaks, threshold = detect_peaks_vectorized(df_filtered, 'kW_Instant', peak_percentile)

    if not peaks.empty:
        st.error(f"⚠️ **DEMAND ALERT**: {len(peaks)} events exceeded the {peak_percentile}th-percentile threshold ({threshold:.2f} kW).")

    fig = go.Figure()
    # Base power trace
    fig.add_trace(go.Scatter(
        x=df_filtered[time_col], y=df_filtered['kW_Instant'],
        name='Power (kW)', line=dict(color='#00B4D8', width=1.5),
        hovertemplate='<b>%{x|%d %b %H:%M}</b><br>Power: %{y:.2f} kW<br>Current: %{customdata:.1f} A<extra></extra>',
        customdata=df_filtered[amp_col]
    ))
    # Threshold dotted line
    fig.add_trace(go.Scatter(
        x=df_filtered[time_col], y=[threshold]*len(df_filtered),
        name=f'Threshold {peak_percentile}%', line=dict(color='orange', dash='dot', width=2), hoverinfo='skip'
    ))
    # Red fill above threshold
    upper_bound = np.maximum(df_filtered['kW_Instant'], threshold)
    fig.add_trace(go.Scatter(
        x=df_filtered[time_col], y=upper_bound,
        fill='tonexty', fillcolor='rgba(255,0,0,0.25)',
        line=dict(width=0), name='Exceedance Zone', hoverinfo='skip'
    ))
    # Peak markers
    if not peaks.empty:
        fig.add_trace(go.Scatter(
            x=peaks[time_col], y=peaks['kW_Instant'], mode='markers',
            name='Peak Event', marker=dict(color='red', size=8, symbol='circle', line=dict(color='white', width=1)),
            hovertemplate='<b>⚠️ PEAK EVENT</b><br>%{x|%d %b %H:%M}<br>Load: %{y:.2f} kW<extra></extra>'
        ))
    fig.update_layout(
        title=f"Triph. Load Evolution - Active Peak Isolation (> {threshold:.2f} kW)",
        template="plotly_dark", hovermode="x unified",
        xaxis_title="Timeline", yaxis_title="Demand Power (kW)",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig, use_container_width=True)

@st.fragment
def render_analisis_turnos(df_filtered, voltage_type):
    st.markdown("<h2 align='center'>👥 Shift Performance Analysis</h2>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        turno_means = df_filtered.groupby('Turno')['kW_Instant'].mean().reset_index()
        turno_means['Turno'] = turno_means['Turno'].astype(str)
        fig = px.bar(
            turno_means, x='Turno', y='kW_Instant', text_auto='.2f',
            color='Turno', color_discrete_sequence=['#00FFAA', '#FF6B6B', '#4ECDC4'],
            title=f"Avg Power per Shift (V={voltage_type}V)"
        )
        fig.update_traces(textposition='outside')
        fig.update_layout(template="plotly_dark", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        turno_sum = df_filtered.groupby('Turno')['kW_Instant'].sum().reset_index()
        turno_sum['Turno'] = turno_sum['Turno'].astype(str)
        fig = px.pie(
            turno_sum, values='kW_Instant', names='Turno', hole=.5,
            color='Turno', color_discrete_sequence=['#00FFAA', '#FF6B6B', '#4ECDC4'],
            title="Energy Share by Shift (%)"
        )
        fig.update_layout(template="plotly_dark")
        st.plotly_chart(fig, use_container_width=True)

    # Estadísticas por turno
    turno_stats = df_filtered.groupby('Turno').agg(
        Avg_kW=('kW_Instant','mean'), Max_kW=('kW_Instant','max'),
        Min_kW=('kW_Instant','min'), Std_kW=('kW_Instant','std')
    ).round(2)
    turno_stats.index = turno_stats.index.map(lambda x: f"Shift {x}")
    st.dataframe(turno_stats, use_container_width=True)

    # ---- Gráfica de líneas por hora desagregada por turno (restaurada) ----
    st.markdown("### 📈 Hourly Consumption Trend by Shift")
    df_hourly = df_filtered.groupby(['Hora', 'Turno'])['kW_Instant'].mean().reset_index()
    df_hourly['Turno'] = df_hourly['Turno'].astype(str)
    fig_hourly = px.line(
        df_hourly, x='Hora', y='kW_Instant', color='Turno', markers=True,
        title="Average Hourly Load per Shift",
        color_discrete_sequence=['#00FFAA', '#FF6B6B', '#4ECDC4'],
        labels={'kW_Instant': 'Avg Power (kW)', 'Hora': 'Hour of Day'}
    )
    fig_hourly.update_xaxes(dtick=1)
    fig_hourly.update_layout(template="plotly_dark", hovermode="x unified")
    # Marcar el pico de cada turno
    for turno_val in df_hourly['Turno'].unique():
        sub = df_hourly[df_hourly['Turno'] == turno_val]
        peak_row = sub.loc[sub['kW_Instant'].idxmax()]
        fig_hourly.add_annotation(
            x=peak_row['Hora'], y=peak_row['kW_Instant'],
            text=f"  {peak_row['kW_Instant']:.1f} kW",
            showarrow=True, arrowhead=2, arrowsize=1, arrowcolor='white',
            font=dict(color='white', size=10)
        )
    st.plotly_chart(fig_hourly, use_container_width=True)

    # Peak por turno
    col_s1, col_s2, col_s3 = st.columns(3)
    for i, turno in enumerate([1, 2, 3]):
        sub = df_hourly[df_hourly['Turno'] == str(turno)]
        if not sub.empty:
            pk = sub.loc[sub['kW_Instant'].idxmax()]
            with [col_s1, col_s2, col_s3][i]:
                st.metric(f"Shift {turno} - Peak Hour", f"{pk['kW_Instant']:.2f} kW",
                          help=f"Peak at {int(pk['Hora']):02d}:00 hrs")

@st.fragment
def render_pdf_exporter(df_filtered, energia_total_kwh, costo_kwh, time_col, report_type='daily'):
    st.markdown(f"<h2 align='center' style='color:#00FFAA;'>📄 {'Daily' if report_type=='daily' else 'Monthly'} Executive PDF Report</h2>", unsafe_allow_html=True)
    
    if st.button(f"Generate {'Daily' if report_type=='daily' else 'Monthly'} Report", use_container_width=True, key=f"pdf_{report_type}"):
        with st.spinner("Compiling structural narrative and rendering visual assets..."):
            try:
                # 1. Gráfica de Barras con Etiquetas
                if report_type == 'daily':
                    chart_bar_df = df_filtered.groupby('Turno')['kW_Instant'].mean().reset_index()
                    chart_bar_df['Label'] = chart_bar_df['Turno'].apply(lambda x: f"Shift {x}")
                    bar_img = create_pdf_chart_image(chart_bar_df, 'Label', 'kW_Instant', 'Average Power Demand per Shift (kW)')
                else:
                    # Mensual: Barras por día
                    chart_bar_df = df_filtered.copy()
                    chart_bar_df['Día_Str'] = chart_bar_df['Día'].astype(str)
                    bar_img = create_pdf_chart_image(chart_bar_df, 'Día_Str', 'Potencia_Promedio_kW', 'Daily Average Consumption Trend (kW)')

                # 2. Gráfica de Líneas con Picos Rojos - exactamente 15 puntos para limpieza visual
                if report_type == 'daily':
                    # Muestreo preciso a 15 puntos equidistantes (sin importar cuantos registros haya)
                    n = len(df_filtered)
                    step = max(1, n // 15)
                    line_df = df_filtered.iloc[::step].head(15).copy()
                    line_img = create_pdf_chart_image(line_df, time_col, 'kW_Instant', 'Power Evolution & Peak Anomalies (15-Point Sample)', 'line', highlight_peaks=True)
                else:
                    line_img = create_pdf_chart_image(df_filtered, 'Día', 'Pico_Maximo_kW', 'Historical Peak Demand Records (Cloud)', 'line', highlight_peaks=True)

                # Construir PDF
                pdf = ExecutivePDF()
                pdf.add_page()

                # ---- 1. Tabla de KPIs del Dashboard (la imagen del dashboard en texto) ----
                pdf.set_font('Helvetica', 'B', 14)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 10, "1. Key Performance Indicators (KPI Summary)", new_x="LMARGIN", new_y="NEXT")
                pdf.ln(2)

                # Calcular datos
                horas_mon = (df_filtered[time_col].max() - df_filtered[time_col].min()).total_seconds() / 3600 if report_type == 'daily' else 0
                avg_power_v = df_filtered['kW_Instant'].mean() if report_type == 'daily' else df_filtered.get('Potencia_Promedio_kW', pd.Series([0])).mean()
                max_peak_v  = df_filtered['kW_Instant'].max()  if report_type == 'daily' else df_filtered.get('Pico_Maximo_kW', pd.Series([0])).max()
                variab_v    = df_filtered['kW_Instant'].std() / max(df_filtered['kW_Instant'].mean(), 0.01) if report_type == 'daily' else 0
                costo_v     = energia_total_kwh * costo_kwh

                # Dibuja tabla de KPIs con fondo de color alternado
                kpi_rows = [
                    ("Active Records",          f"{len(df_filtered):,} samples"),
                    ("Average Power Demand",     f"{avg_power_v:.2f} kW"),
                    ("Total Energy Consumed",    f"{energia_total_kwh:,.2f} kWh"),
                    ("Monitoring Duration",      f"{horas_mon:.1f} hrs" if report_type == 'daily' else f"{len(df_filtered)} days"),
                    ("Maximum Peak Demand",      f"{max_peak_v:.2f} kW"),
                    ("Demand Variability (CoV)", f"{variab_v:.1%}"),
                    ("Estimated Operational Cost", f"${costo_v:,.2f} MXN  (@ ${costo_kwh:.2f}/kWh)"),
                ]

                col_w_label = 90
                col_w_value = 90
                row_h       = 8
                pdf.set_font('Helvetica', '', 10)
                for i, (label, value) in enumerate(kpi_rows):
                    if i % 2 == 0:
                        pdf.set_fill_color(235, 250, 255)   # azul muy claro
                    else:
                        pdf.set_fill_color(255, 255, 255)   # blanco
                    pdf.set_text_color(40, 40, 40)
                    pdf.cell(col_w_label, row_h, label, border=1, fill=True)
                    pdf.set_font('Helvetica', 'B', 10)
                    pdf.cell(col_w_value, row_h, value, border=1, fill=True, new_x="LMARGIN", new_y="NEXT")
                    pdf.set_font('Helvetica', '', 10)

                # Horas pico en tabla
                if report_type == 'daily':
                    peak_hrs = df_filtered.groupby('Hora')['kW_Instant'].max().nlargest(3)
                    peak_hrs_str = ", ".join([f"{int(h):02d}:00 ({v:.1f} kW)" for h, v in peak_hrs.items()])
                    pdf.set_fill_color(255, 240, 240)
                    pdf.set_font('Helvetica', '', 10)
                    pdf.cell(col_w_label, row_h, "Top 3 Peak Demand Hours", border=1, fill=True)
                    pdf.set_font('Helvetica', 'B', 10)
                    pdf.cell(col_w_value, row_h, sanitize_pdf(peak_hrs_str), border=1, fill=True, new_x="LMARGIN", new_y="NEXT")

                pdf.ln(10)

                # ---- 2. Executive Narrative ----
                pdf.set_font('Helvetica', 'B', 14)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 10, "2. Executive Summary", new_x="LMARGIN", new_y="NEXT")
                pdf.set_font('Helvetica', '', 11)
                pdf.set_text_color(40, 40, 40)

                date_start = df_filtered[time_col].min().strftime('%B %d, %Y') if report_type == 'daily' else df_filtered['Dia'].min().strftime('%B %d, %Y')
                date_end   = df_filtered[time_col].max().strftime('%B %d, %Y') if report_type == 'daily' else df_filtered['Dia'].max().strftime('%B %d, %Y')

                if report_type == 'daily':
                    worst_shift = df_filtered.groupby('Turno')['kW_Instant'].mean().idxmax()
                    best_shift  = df_filtered.groupby('Turno')['kW_Instant'].mean().idxmin()
                    max_kw      = df_filtered['kW_Instant'].max()
                    avg_kw      = df_filtered['kW_Instant'].mean()
                    variability = df_filtered['kW_Instant'].std() / max(avg_kw, 0.01)
                    peak_hrs2   = df_filtered.groupby('Hora')['kW_Instant'].max().nlargest(3)
                    top_hrs_str = ", ".join([f"{int(h):02d}:00 ({v:.1f} kW)" for h, v in peak_hrs2.items()])
                    stability   = "indicating potential instability" if variability > 0.3 else "reflecting stable and predictable operation"
                    narrative = (
                        f"This operational report covers the electrical behavior of monitored systems from {date_start} to {date_end}. "
                        f"A total of {len(df_filtered):,} measurement records were analyzed using trapezoidal numerical integration, "
                        f"yielding a total energy expenditure of {energia_total_kwh:,.2f} kWh over {horas_mon:.1f} hours of continuous monitoring, "
                        f"equivalent to a projected operational cost of ${costo_v:,.2f} MXN at the configured tariff of ${costo_kwh:.2f} MXN/kWh.\n\n"
                        f"The average power demand registered was {avg_power_v:.2f} kW, with an absolute maximum peak of {max_kw:.2f} kW. "
                        f"Shift {worst_shift} registered the highest average electrical load, while Shift {best_shift} maintained the most efficient consumption profile. "
                        f"System demand variability (Coefficient of Variation) was measured at {variability:.1%}, {stability}. "
                        f"The three highest-demand hours were: {top_hrs_str}. "
                        f"These intervals represent the primary risk windows for tariff penalties and equipment overloading."
                    )
                else:
                    total_days = len(df_filtered)
                    avg_peak   = df_filtered['Pico_Maximo_kW'].mean() if 'Pico_Maximo_kW' in df_filtered.columns else 0
                    abs_peak   = df_filtered['Pico_Maximo_kW'].max()  if 'Pico_Maximo_kW' in df_filtered.columns else 0
                    narrative = (
                        f"This monthly summary covers {total_days} operational days from {date_start} to {date_end}. "
                        f"Cloud-synchronized records indicate a total estimated energy consumption of {energia_total_kwh:,.2f} kWh, "
                        f"representing a cumulative infrastructure cost of ${costo_v:,.2f} MXN at ${costo_kwh:.2f} MXN/kWh.\n\n"
                        f"The average daily peak demand was {avg_peak:.2f} kW, with an absolute monthly maximum of {abs_peak:.2f} kW. "
                        f"Days flagged with red markers in the Peak Analysis chart require priority maintenance evaluation "
                        f"to prevent tariff penalty surcharges and accelerated thermal wear on critical equipment."
                    )

                narrative = sanitize_pdf(narrative)
                pdf.multi_cell(0, 6, narrative)
                pdf.ln(8)

                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 14)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 10, "3. Load Distribution & Average Demand", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(40, 40, 40)
                pdf.image(bar_img, w=180)
                pdf.ln(8)

                pdf.add_page()
                pdf.set_font('Helvetica', 'B', 14)
                pdf.set_text_color(0, 180, 216)
                pdf.cell(0, 10, "4. Critical Peak Analysis - Red Alert Zones", new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(40, 40, 40)
                pdf.image(line_img, w=180)

                pdf.ln(8)
                pdf.set_font('Helvetica', 'I', 10)
                pdf.multi_cell(0, 6,
                    "Note: Red data points represent demand events that significantly exceeded the operational baseline (120% of average). "
                    "Each labeled value indicates the measured power at that specific moment. "
                    "These anomalies are flagged for immediate review by the Maintenance and Energy Management teams to prevent "
                    "system overloading, tariff penalties, and accelerated equipment degradation.")

                pdf_bytes = bytes(pdf.output())
                os.remove(bar_img)
                os.remove(line_img)
                
                st.success("Report Compiled Successfully!")
                st.download_button(label=f"📥 Download {report_type.capitalize()} Report PDF", data=pdf_bytes, file_name=f"Executive_{report_type}_Report.pdf", mime="application/pdf")

            except Exception as e:
                st.error(f"Error compiling PDF: {str(e)}")
                st.code(traceback.format_exc())

@st.fragment
def render_monthly_insights(costo_kwh):
    st.markdown("<h2 align='center' style='color:#7F56D9;'>📅 Monthly Cloud Analysis (Supabase)</h2>", unsafe_allow_html=True)
    
    if not supabase_client:
        st.warning("Cloud Sync is not configured.")
        return

    with st.spinner("Fetching historical data from Supabase Cloud..."):
        try:
            # Traer los datos de la tabla sincronizada
            response = supabase_client.table('hobo_monthly_sync').select("*").order("Día", desc=False).execute()
            cloud_raw = response.data
            
            if not cloud_raw:
                st.info("No historical data found in Supabase. Please synchronize some data first.")
                return
            
            df_cloud = pd.DataFrame(cloud_raw)
            df_cloud['Día'] = pd.to_datetime(df_cloud['Día'])
            
            # KPIs Mensuales
            col1, col2, col3 = st.columns(3)
            with col1:
                total_days = len(df_cloud)
                st.metric("Total Days Recorded", total_days)
            with col2:
                avg_mo_pow = df_cloud['Potencia_Promedio_kW'].mean()
                st.metric("Monthly Avg Power", f"{avg_mo_pow:.2f} kW")
            with col3:
                abs_max_peak = df_cloud['Pico_Maximo_kW'].max()
                st.metric("Absolute Monthly Peak", f"{abs_max_peak:.2f} kW")

            # Gráfica Mensual (Consumo diario)
            st.markdown("### Historical Energy Consumption (Daily Averages)")
            fig_mo = px.bar(df_cloud, x='Día', y='Potencia_Promedio_kW', color='Potencia_Promedio_kW', color_continuous_scale='Viridis')
            fig_mo.update_layout(template="plotly_dark")
            st.plotly_chart(fig_mo, use_container_width=True)

            # Gráfica de Picos Máximos Diarios
            st.markdown("### Peak Demand Evolution (Historical)")
            fig_line_mo = px.line(df_cloud, x='Día', y='Pico_Maximo_kW', markers=True, title="Max Daily Peaks Trend")
            fig_line_mo.add_hline(y=df_cloud['Pico_Maximo_kW'].quantile(0.9), line_dash="dash", line_color="red", annotation_text="P90 Peak Alert")
            fig_line_mo.update_layout(template="plotly_dark")
            st.plotly_chart(fig_line_mo, use_container_width=True)

            # Sección de Reporte Mensual
            st.markdown("---")
            # Supongamos que queremos calcular una energía mensual aproximada para el reporte
            # Como tenemos promedios diarios, energía aprox = Promedio_kW * 24 horas cada día
            energy_est_mo = (df_cloud['Potencia_Promedio_kW'] * 24).sum()
            render_pdf_exporter(df_cloud, energy_est_mo, costo_kwh, 'Día', report_type='monthly')

        except Exception as e:
            st.error(f"Failed to fetch cloud data: {str(e)}")

@st.fragment
def render_cloud_sync(df_filtered):
    st.markdown("<h2 align='center' style='color:#7F56D9;'>☁️ Cloud Data Synchronization</h2>", unsafe_allow_html=True)
    if not supabase_client:
        st.warning("Supabase configuration missing.")
        return
        
    if st.button("🚀 Push to Supabase Cloud", type="primary"):
        with st.spinner("Encrypting and uploading data segments..."):
            try:
                daily_data = df_filtered.groupby('Día').agg(
                    Potencia_Promedio_kW=('kW_Instant', 'mean'),
                    Pico_Maximo_kW=('kW_Instant', 'max')
                ).reset_index()
                daily_data['Día'] = daily_data['Día'].astype(str)
                records = daily_data.to_dict(orient='records')
                supabase_client.table('hobo_monthly_sync').insert(records).execute()
                st.success("Successfully synchronized to the cloud!")
            except Exception as ex:
                st.error(f"Sync failed: {str(ex)}")

# --- MAIN APP FLOW ---
colA, colB = st.columns([1, 8])
with colA:
    try:
        logo = Image.open("EA_2.png")
        st.image(logo, use_container_width=True)
    except: pass
with colB: 
    st.markdown("<h1 align='center' style='padding-top:20px; font-weight:800;'>Enterprise Energy Analyzer</h1>", unsafe_allow_html=True)
    st.markdown("<div align='center'><span style='color: #00FFAA; letter-spacing: 2px;'>POWERED BY HOBO & VECTOR-CORE ENGINE</span></div>", unsafe_allow_html=True)

st.markdown("---")

with st.sidebar:
    st.markdown("### 📡 Data Intake")
    uploaded_file = st.file_uploader("Upload HOBO Report (CSV/XLSX)", type=["csv", "xlsx"])

if not uploaded_file:
    st.markdown("""<div style="text-align: center; padding: 50px; background-color: #1a1e23; border-radius: 15px; border: 1px solid #333;">
            <h1 style="color: #4a4e53; font-size: 60px;">🚀</h1><h2 style="color: #e0e6ed;">System Ready & Waiting</h2>
            <p style="color: #9aa0a6; font-size: 18px; max-width: 600px; margin: 0 auto;">Upload your data file to begin. Vector-Core will process thousands of records instantly.</p><br>
            <p style="color: #00B4D8; font-weight: bold; font-size: 15px;">🐍 Developed in Python by Master Engineer Erik Armenta</p>
            <hr style="border-color:#333; margin: 20px auto; width: 50%;"><p style="color: #666; font-size: 14px;">Mastering industrial Amperage into executive insights.</p></div>""", unsafe_allow_html=True)
    st.stop()

try:
    file_bytes = uploaded_file.getvalue()
    ext = uploaded_file.name.split('.')[-1].lower()
    df_raw, t_col, a_col = load_hobo_data_from_bytes(file_bytes, ext)
except Exception as e:
    st.error(f"Critical error: {str(e)}"); st.stop()

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

if df_filt.empty: st.warning("No results found."); st.stop()
e_total = calculate_energy_vectorized(df_filt, t_col, 'kW_Instant')

if selected_page == "KPI Dashboard": render_kpi_dashboard(df_filt, t_col, a_col, e_total, costo_kwh)
elif selected_page == "Trends & Peaks": render_tendencias_picos(df_filt, t_col, a_col, peak_sens)
elif selected_page == "Behaviors": render_analisis_turnos(df_filt, volt)
elif selected_page == "Monthly Insights": render_monthly_insights(costo_kwh)
elif selected_page == "Executive PDF": render_pdf_exporter(df_filt, e_total, costo_kwh, t_col, 'daily')
elif selected_page == "Cloud Sync": render_cloud_sync(df_filt)

st.markdown("<p style='text-align: right; color:#555; font-size:12px;'>Vector-Core Engine v5.1 | Supabase Cloud Edition</p>", unsafe_allow_html=True)
