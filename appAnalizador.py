# -*- coding: utf-8 -*-
"""
Created on Fri Apr 10 13:30:20 2026
Updated: Powerful Industrial Energy Analyzer for HOBO Data

@author: acer
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import altair as alt
from datetime import datetime, timedelta
from PIL import Image
import re
import traceback

# Configuración de la página
st.set_page_config(page_title="EA Energy Analyzer", layout="wide", page_icon="⚡")

# --- FUNCIONES DE PROCESAMIENTO ---
def load_hobo_data(file):
    """Carga específica para archivos HOBO con estructura especial"""
    extension = file.name.split('.')[-1]

    try:
        if extension == 'csv':
            # Leer todo el contenido como texto para procesar manualmente
            content = file.getvalue().decode('utf-8')
            lines = content.split('\n')

            # Encontrar la primera línea que contiene datos numéricos reales
            data_start = 0
            for i, line in enumerate(lines):
                # Buscar línea que tenga formato de fecha (ej: 3/20/2026)
                if re.search(r'\d+/\d+/\d+', line):
                    data_start = i
                    break

            # Si no encontramos fecha, empezar desde línea 3 (saltando encabezados)
            if data_start == 0:
                data_start = 3

            # Tomar solo las líneas de datos desde data_start
            data_lines = lines[data_start:]

            # Procesar cada línea
            parsed_data = []
            for line in data_lines:
                if line.strip():
                    # Limpiar la línea: remover comillas y caracteres especiales
                    clean_line = line.replace('"', '').strip()
                    # Separar por tabulación
                    parts = clean_line.split('\t')
                    if len(parts) >= 2:
                        # Tomar solo las primeras 3 columnas útiles (índice, fecha, valor)
                        parsed_data.append(parts[:3])

            # Crear DataFrame
            if parsed_data:
                df = pd.DataFrame(parsed_data)
                # Asignar nombres de columnas
                df.columns = ['Index', 'DateTime', 'Amperios']

                # Convertir DateTime
                df['DateTime'] = pd.to_datetime(df['DateTime'], errors='coerce')

                # Convertir Amperios a numérico
                df['Amperios'] = pd.to_numeric(df['Amperios'], errors='coerce')

                # Eliminar filas con valores nulos
                df = df.dropna(subset=['DateTime', 'Amperios'])

                # Eliminar columna de índice
                df = df.drop(columns=['Index'])

                # Resetear índice
                df = df.reset_index(drop=True)

                # Mostrar información de depuración
                st.success(f"✅ Cargados {len(df)} registros desde el archivo")

                return df, 'DateTime', 'Amperios'
            else:
                st.error("No se encontraron datos en el archivo")
                return pd.DataFrame(), None, None

        else:  # Excel
            df = pd.read_excel(file, skiprows=2)
            df.columns = [str(col).strip() for col in df.columns]
            time_col = df.columns[1] if len(df.columns) > 1 else df.columns[0]
            amp_col = df.columns[2] if len(df.columns) > 2 else df.columns[1]

            # Convertir la columna de tiempo a datetime
            df[time_col] = pd.to_datetime(df[time_col], errors='coerce')

            # Convertir la columna de amperaje a numérico
            df[amp_col] = pd.to_numeric(df[amp_col], errors='coerce')

            # Eliminar filas con tiempo nulo
            df = df.dropna(subset=[time_col])

            # Resetear índice
            df = df.reset_index(drop=True)

            # Renombrar columnas
            df.rename(columns={time_col: 'DateTime', amp_col: 'Amperios'}, inplace=True)

            return df, 'DateTime', 'Amperios'

    except Exception as e:
        st.error(f"Error detallado al cargar el archivo: {str(e)}")
        st.code(traceback.format_exc())
        return pd.DataFrame(), None, None

def assign_shift(dt):
    """Asigna turno basado en la hora del día"""
    if pd.isna(dt):
        return 0
    hour = dt.hour
    if 6 <= hour < 14:
        return 1  # Turno matutino
    elif 14 <= hour < 22:
        return 2  # Turno vespertino
    else:
        return 3  # Turno nocturno

def calculate_kw(amps, voltage, pf=0.9):
    """Calcula kW a partir de Amperios, Voltaje y Factor de Potencia"""
    if pd.isna(amps) or amps <= 0:
        return 0
    # Fórmula trifásica: kW = (V * I * PF * √3) / 1000
    return (voltage * amps * pf * 1.732) / 1000

def calculate_energy(df, time_col, power_col):
    """Calcula energía usando integración numérica (Regla del Trapecio)"""
    if df.empty or len(df) < 2:
        return 0

    # Ordenar por tiempo
    df = df.sort_values(time_col).reset_index(drop=True)

    # Calcular delta tiempo en horas
    time_diff = df[time_col].diff().dt.total_seconds() / 3600

    # Regla del trapecio
    energy = 0
    for i in range(1, len(df)):
        delta_t = time_diff.iloc[i]
        if delta_t > 0 and delta_t < 1:  # Evitar saltos grandes
            avg_power = (df[power_col].iloc[i] + df[power_col].iloc[i-1]) / 2
            energy += avg_power * delta_t

    return energy

def detect_peaks(df, column, percentile=95):
    """Detecta picos de demanda usando percentil"""
    if df.empty or column not in df.columns:
        return pd.DataFrame(), 0

    threshold = df[column].quantile(percentile/100)
    peaks = df[df[column] > threshold].copy()
    if not peaks.empty:
        peaks['peak_magnitude'] = peaks[column] - threshold
    return peaks, threshold

# --- INTERFAZ ---
# Logo personalizado
try:
    logo = Image.open("EA_2.png")
    col_logo, col_title = st.columns([1, 5])
    with col_logo:
        st.image(logo, width=100)
    with col_title:
        st.title("⚡ EA Energy Analyzer")
except:
    st.title("⚡ EA Energy Analyzer")

st.markdown("---")

uploaded_file = st.file_uploader("📁 Carga tu reporte de HOBO (CSV o Excel)", type=["csv", "xlsx"])

if uploaded_file:
    # Cargar datos con la función especial para HOBO
    df, time_col, amp_col = load_hobo_data(uploaded_file)

    if df.empty:
        st.error("❌ No se pudieron cargar los datos. Verifica el formato del archivo.")
        st.stop()

    # Mostrar vista previa de los datos
    with st.expander("🔍 Vista previa de los datos cargados"):
        st.dataframe(df.head(10))
        st.write(f"Total de registros: {len(df)}")
        st.write(f"Rango de fechas: desde {df[time_col].min()} hasta {df[time_col].max()}")

    # --- CONFIGURACIÓN DE VOLTAJE ---
    st.sidebar.header("⚙️ Configuración Eléctrica")
    voltage_type = st.sidebar.selectbox(
        "Selecciona el voltaje del sistema:",
        [480, 220, 110],
        index=0,
        help="Selecciona el voltaje nominal para calcular kW a partir de Amperios"
    )

    # Factor de potencia por defecto
    pf = st.sidebar.number_input("Factor de Potencia (PF):", min_value=0.5, max_value=1.0, value=0.9, step=0.01)

    # Calcular kW a partir de Amperios
    df['kW_Instant'] = df[amp_col].apply(lambda x: calculate_kw(x, voltage_type, pf))

    # Asignar turnos automáticamente
    df['Turno'] = df[time_col].apply(assign_shift)

    # --- BARRA LATERAL DE FILTROS ---
    st.sidebar.header("🎯 Filtros Avanzados")

    # Filtro de Rango de Fechas
    min_date = df[time_col].min()
    max_date = df[time_col].max()

    if pd.notna(min_date) and pd.notna(max_date):
        min_date_val = min_date.date()
        max_date_val = max_date.date()

        rango = st.sidebar.date_input("📅 Selecciona el periodo:", [min_date_val, max_date_val])
    else:
        st.sidebar.warning("⚠️ No hay fechas válidas en los datos")
        rango = []

    # Filtro de Turnos
    turnos_sel = st.sidebar.multiselect("👥 Turnos a analizar:", [1, 2, 3], default=[1, 2, 3])

    # Umbral de picos
    peak_percentile = st.sidebar.slider("🎯 Sensibilidad para detección de picos (Percentil)", 80, 99, 95, 1)

    # Aplicar filtros
    df_filtered = df[df['Turno'].isin(turnos_sel)].copy()

    if len(rango) == 2 and pd.notna(min_date) and pd.notna(max_date):
        mask = (df_filtered[time_col].dt.date >= rango[0]) & (df_filtered[time_col].dt.date <= rango[1])
        df_filtered = df_filtered.loc[mask]

    if df_filtered.empty:
        st.warning("⚠️ No hay datos en el rango seleccionado. Ajusta los filtros.")
        st.stop()

    # --- CÁLCULO AUTOMÁTICO DE ENERGÍA ---
    st.sidebar.markdown("---")
    st.sidebar.subheader("🔋 Cálculo de Energía")

    energia_total = calculate_energy(df_filtered, time_col, 'kW_Instant')
    st.sidebar.metric(
        f"Energía Total Consumida",
        f"{energia_total:.2f} kWh",
        help=f"Calculado mediante integración numérica (Regla del Trapecio) a partir de kW instantáneos. Voltaje: {voltage_type}V, PF: {pf}"
    )

    # --- KPIs PRINCIPALES ---
    st.subheader("📊 Indicadores Clave de Rendimiento")
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric("📈 Registros Totales", f"{len(df_filtered):,}")
    with col2:
        promedio_kw = df_filtered['kW_Instant'].mean()
        st.metric(f"⚡ Potencia Promedio", f"{promedio_kw:.2f} kW")
    with col3:
        promedio_amps = df_filtered[amp_col].mean()
        st.metric(f"🔌 Corriente Promedio", f"{promedio_amps:.2f} A")
    with col4:
        if pd.notna(min_date) and pd.notna(max_date):
            horas = (df_filtered[time_col].max() - df_filtered[time_col].min()).total_seconds() / 3600
            st.metric("⏱️ Duración Monitoreo", f"{horas:.1f} horas")
    with col5:
        max_kw = df_filtered['kW_Instant'].max()
        st.metric("🔴 Pico Máximo", f"{max_kw:.2f} kW")

    # --- GRÁFICA CON PLOTLY Y DETECCIÓN DE PICOS ---
    st.subheader("📈 Análisis Temporal con Detección de Picos")

    fig = go.Figure()

    # Detectar picos
    peaks, threshold = detect_peaks(df_filtered, 'kW_Instant', peak_percentile)

    # Línea principal
    fig.add_trace(go.Scatter(
        x=df_filtered[time_col],
        y=df_filtered['kW_Instant'],
        mode='lines',
        name=f'Potencia (kW)',
        line=dict(width=2, color='#00B4D8'),
        hovertemplate='<b>Tiempo</b>: %{x|%Y-%m-%d %H:%M}<br>' +
                      '<b>Potencia</b>: %{y:.2f} kW<br>' +
                      '<b>Corriente</b>: %{customdata:.1f} A<br>' +
                      '<b>Turno</b>: %{text}<extra></extra>',
        customdata=df_filtered[amp_col],
        text=df_filtered['Turno']
    ))

    # Marcar picos en rojo
    if not peaks.empty:
        fig.add_trace(go.Scatter(
            x=peaks[time_col],
            y=peaks['kW_Instant'],
            mode='markers',
            name=f'⚠️ Picos de Demanda',
            marker=dict(
                color='red',
                size=12,
                symbol='circle',
                line=dict(color='darkred', width=2)
            ),
            hovertemplate='<b>⚠️ ALERTA - PICO DE DEMANDA ⚠️</b><br>' +
                          '<b>Tiempo</b>: %{x|%Y-%m-%d %H:%M}<br>' +
                          '<b>Potencia</b>: %{y:.2f} kW<br>' +
                          '<b>Corriente</b>: %{customdata:.1f} A<br>' +
                          '<b>Exceso</b>: %{text:.2f} kW sobre umbral<br>' +
                          '<b>Turno</b>: %{meta}<extra></extra>',
            customdata=peaks[amp_col],
            text=peaks['peak_magnitude'],
            meta=peaks['Turno']
        ))

    # Línea de umbral
    fig.add_hline(
        y=threshold,
        line_dash="dash",
        line_color="orange",
        annotation_text=f"⚠️ Umbral {peak_percentile}%: {threshold:.2f} kW",
        annotation_position="top right"
    )

    fig.update_layout(
        title=f"Comportamiento de Carga Eléctrica - Horno de Fundas (Convertido de Amperios a kW)",
        xaxis_title="Tiempo",
        yaxis_title="Potencia (kW)",
        template="plotly_dark",
        hovermode="x unified",
        hoverlabel=dict(
            bgcolor="rgba(0,0,0,0.9)",
            font_size=13,
            font_family="Arial Black"
        ),
        legend=dict(
            yanchor="top",
            y=0.99,
            xanchor="left",
            x=0.01,
            bgcolor="rgba(0,0,0,0.5)"
        )
    )

    st.plotly_chart(fig, use_container_width=True)

    # Mostrar estadísticas de picos
    if not peaks.empty:
        st.error(f"⚠️ **ALERTA DE PUNTOS CRÍTICOS**: Se detectaron {len(peaks)} eventos de demanda máxima. " +
                f"El pico más alto fue de {peaks['kW_Instant'].max():.2f} kW " +
                f"({peaks[amp_col].max():.1f} A) el día {peaks[time_col].min().strftime('%Y-%m-%d %H:%M')}")

    # --- COMPARATIVA DE TURNOS ---
    st.subheader("👥 Comparativa por Turnos")

    turno_stats = df_filtered.groupby('Turno').agg({
        'kW_Instant': ['mean', 'max', 'min', 'std'],
        amp_col: ['mean', 'max']
    }).round(2)

    # Renombrar columnas
    turno_stats.columns = ['Potencia Promedio (kW)', 'Potencia Máx (kW)', 'Potencia Mín (kW)', 'Desv Estándar', 'Corriente Prom (A)', 'Corriente Máx (A)']

    # Gráfico de barras por turno
    turno_means = df_filtered.groupby('Turno')['kW_Instant'].mean().reset_index()
    fig_bar = px.bar(
        turno_means,
        x='Turno',
        y='kW_Instant',
        title=f'Potencia Promedio por Turno (Voltaje: {voltage_type}V)',
        text='kW_Instant',
        color='Turno',
        color_discrete_sequence=px.colors.qualitative.Set2,
        labels={'kW_Instant': 'kW Promedio', 'Turno': 'Turno de Trabajo'}
    )
    fig_bar.update_traces(texttemplate='%{text:.2f} kW', textposition='outside')
    fig_bar.update_layout(template="plotly_dark")
    st.plotly_chart(fig_bar, use_container_width=True)

    # Mostrar tabla estadística
    st.dataframe(turno_stats, use_container_width=True)

    # --- GRÁFICA DE ALTAR: PROMEDIO DE CONSUMO POR HORA (kWh/h) ---
    st.subheader("📈 Tendencia de Consumo Promedio por Hora (Altair)")

    # Preparar datos para Altair - Agrupar por hora y calcular promedio
    df_hourly = df_filtered.groupby(df_filtered[time_col].dt.hour).agg({
        'kW_Instant': 'mean'
    }).reset_index()
    df_hourly.columns = ['Hora', 'Potencia_Promedio_kW']

    # También calcular por turno para comparativa
    df_hourly_by_shift = df_filtered.groupby([
        df_filtered[time_col].dt.hour,
        'Turno'
    ])['kW_Instant'].mean().reset_index()
    df_hourly_by_shift.columns = ['Hora', 'Turno', 'Potencia_Promedio_kW']

    # Crear selector para tipo de vista
    view_type = st.radio(
        "Selecciona vista:",
        ['Vista General (Todas las horas)', 'Vista por Turno'],
        horizontal=True
    )

    if view_type == 'Vista General (Todas las horas)':
        # Crear área y línea por separado y luego combinarlas
        area = alt.Chart(df_hourly).mark_area(
            opacity=0.3,
            color='#00FFAA'
        ).encode(
            x=alt.X('Hora:Q',
                    title='Hora del Día',
                    axis=alt.Axis(format='d', tickMinStep=1, titleColor='white', labelColor='white')),
            y=alt.Y('Potencia_Promedio_kW:Q',
                    title='Potencia Promedio (kW)',
                    scale=alt.Scale(zero=False),
                    axis=alt.Axis(titleColor='white', labelColor='white'))
        )

        line = alt.Chart(df_hourly).mark_line(
            stroke='#00FFAA',
            strokeWidth=3
        ).encode(
            x='Hora:Q',
            y='Potencia_Promedio_kW:Q'
        )

        points = alt.Chart(df_hourly).mark_point(
            filled=True,
            color='#00FFAA',
            size=100
        ).encode(
            x='Hora:Q',
            y='Potencia_Promedio_kW:Q',
            tooltip=[
                alt.Tooltip('Hora:Q', title='Hora'),
                alt.Tooltip('Potencia_Promedio_kW:Q', title='Potencia Promedio (kW)', format='.2f')
            ]
        )

        # Combinar todas las capas
        chart = (area + line + points).properties(
            title={
                'text': 'Consumo Promedio por Hora del Día',
                'fontSize': 16,
                'fontWeight': 'bold',
                'color': 'white'
            },
            height=400,
            background='#1E1E1E'
        ).configure_view(
            strokeWidth=0
        )

        st.altair_chart(chart, use_container_width=True)

        # Mostrar las horas pico
        top_hours = df_hourly.nlargest(3, 'Potencia_Promedio_kW')
        st.info(f"💡 **Horas de mayor consumo promedio:** " +
                ", ".join([f"{int(row['Hora'])}:00 ({row['Potencia_Promedio_kW']:.2f} kW)"
                          for _, row in top_hours.iterrows()]))

    else:
        # Gráfico de líneas por turno con Altair
        # Definir colores por turno
        line_by_shift = alt.Chart(df_hourly_by_shift).mark_line(
            strokeWidth=2.5
        ).encode(
            x=alt.X('Hora:Q',
                    title='Hora del Día',
                    axis=alt.Axis(format='d', tickMinStep=1, titleColor='white', labelColor='white')),
            y=alt.Y('Potencia_Promedio_kW:Q',
                    title='Potencia Promedio (kW)',
                    scale=alt.Scale(zero=False),
                    axis=alt.Axis(titleColor='white', labelColor='white')),
            color=alt.Color('Turno:N',
                           scale=alt.Scale(domain=[1, 2, 3], range=['#00FFAA', '#FF6B6B', '#4ECDC4']),
                           legend=alt.Legend(title="Turno", titleColor='white', labelColor='white')),
        )

        points_by_shift = alt.Chart(df_hourly_by_shift).mark_point(
            filled=True,
            size=80
        ).encode(
            x='Hora:Q',
            y='Potencia_Promedio_kW:Q',
            color=alt.Color('Turno:N',
                           scale=alt.Scale(domain=[1, 2, 3], range=['#00FFAA', '#FF6B6B', '#4ECDC4'])),
            tooltip=[
                alt.Tooltip('Hora:Q', title='Hora'),
                alt.Tooltip('Turno:N', title='Turno'),
                alt.Tooltip('Potencia_Promedio_kW:Q', title='Potencia Promedio (kW)', format='.2f')
            ]
        )

        chart_by_shift = (line_by_shift + points_by_shift).properties(
            title={
                'text': 'Consumo Promedio por Hora - Comparativa por Turno',
                'fontSize': 16,
                'fontWeight': 'bold',
                'color': 'white'
            },
            height=400,
            background='#1E1E1E'
        ).configure_view(
            strokeWidth=0
        )

        st.altair_chart(chart_by_shift, use_container_width=True)

        # Mostrar análisis por turno
        col_shift1, col_shift2, col_shift3 = st.columns(3)
        for turno in [1, 2, 3]:
            turno_data = df_hourly_by_shift[df_hourly_by_shift['Turno'] == turno]
            if not turno_data.empty:
                max_hour = turno_data.loc[turno_data['Potencia_Promedio_kW'].idxmax()]
                with [col_shift1, col_shift2, col_shift3][turno-1]:
                    st.metric(
                        f"Turno {turno} - Pico Máximo",
                        f"{max_hour['Potencia_Promedio_kW']:.2f} kW",
                        help=f"Máximo consumo a las {int(max_hour['Hora'])}:00"
                    )

    # --- TABLA PIVOTE CON DRILL-DOWN ---
    st.subheader("📊 Tabla Pivote Interactiva con Drill-Down")

    # Selector de nivel de agregación
    drill_level = st.radio(
        "Nivel de detalle:",
        ['Por Hora', 'Por Día', 'Por Turno', 'Por Hora y Turno'],
        horizontal=True
    )

    # Crear columnas de tiempo para drill-down
    df_filtered['Hora'] = df_filtered[time_col].dt.hour
    df_filtered['Día'] = df_filtered[time_col].dt.date

    try:
        if drill_level == 'Por Hora':
            pivot_table = pd.pivot_table(
                df_filtered,
                values=['kW_Instant', amp_col],
                index=['Hora'],
                aggfunc={'kW_Instant': ['mean', 'max', 'sum'], amp_col: ['mean', 'max']}
            ).round(2)
        elif drill_level == 'Por Día':
            pivot_table = pd.pivot_table(
                df_filtered,
                values=['kW_Instant', amp_col],
                index=['Día'],
                aggfunc={'kW_Instant': ['mean', 'max', 'sum'], amp_col: ['mean', 'max']}
            ).round(2)
        elif drill_level == 'Por Hora y Turno':
            pivot_table = pd.pivot_table(
                df_filtered,
                values=['kW_Instant', amp_col],
                index=['Turno', 'Hora'],
                aggfunc={'kW_Instant': ['mean', 'max'], amp_col: ['mean']}
            ).round(2)
        else:  # Por Turno
            pivot_table = pd.pivot_table(
                df_filtered,
                values=['kW_Instant', amp_col],
                index=['Turno'],
                aggfunc={'kW_Instant': ['mean', 'max', 'min', 'std', 'sum'], amp_col: ['mean', 'max', 'min']}
            ).round(2)

        # Mostrar tabla
        st.dataframe(pivot_table, use_container_width=True, height=400)

        # Botón de exportación
        csv = pivot_table.to_csv()
        st.download_button(
            label="📥 Descargar Tabla Pivote (CSV)",
            data=csv,
            file_name=f"energy_analysis_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )
    except Exception as e:
        st.warning(f"Error al generar tabla pivote: {str(e)}")

    # --- ANÁLISIS DE DISTRIBUCIÓN ---
    st.subheader("📊 Distribución de Consumo por Turno")

    # Histograma interactivo con facetas por turno
    fig_hist = px.histogram(
        df_filtered,
        x='kW_Instant',
        color='Turno',
        facet_col='Turno',
        nbins=50,
        title=f'Distribución de Potencia - Voltaje: {voltage_type}V, PF: {pf}',
        labels={'kW_Instant': 'Potencia (kW)', 'count': 'Frecuencia'},
        opacity=0.7,
        color_discrete_sequence=px.colors.qualitative.Set2
    )
    fig_hist.update_layout(template="plotly_dark", showlegend=False)
    fig_hist.update_xaxes(title_text="Potencia (kW)")
    fig_hist.update_yaxes(title_text="Frecuencia")
    st.plotly_chart(fig_hist, use_container_width=True)

    # --- GRÁFICA DE CORRIENTE VS POTENCIA ---
    st.subheader("🔄 Relación Corriente vs Potencia")

    fig_scatter = px.scatter(
        df_filtered,
        x=amp_col,
        y='kW_Instant',
        color='Turno',
        title=f'Correlación Amperios → kW (Voltaje: {voltage_type}V, PF: {pf})',
        labels={amp_col: 'Corriente (Amperios)', 'kW_Instant': 'Potencia (kW)'},
        trendline="ols",
        opacity=0.6
    )
    fig_scatter.update_layout(template="plotly_dark")
    st.plotly_chart(fig_scatter, use_container_width=True)

    # --- MÉTRICAS ADICIONALES DE EFICIENCIA ---
    st.subheader("🎯 Recomendaciones de Eficiencia Energética")

    col_rec1, col_rec2, col_rec3 = st.columns(3)

    # Identificar turno con mayor consumo
    worst_shift = df_filtered.groupby('Turno')['kW_Instant'].mean().idxmax()
    best_shift = df_filtered.groupby('Turno')['kW_Instant'].mean().idxmin()

    with col_rec1:
        st.info(f"💡 **Turno Crítico**: Turno {worst_shift} tiene el consumo más alto")
        st.info(f"✅ **Turno Eficiente**: Turno {best_shift} tiene el consumo más bajo")

    with col_rec2:
        # Calcular variabilidad
        variability = df_filtered['kW_Instant'].std() / df_filtered['kW_Instant'].mean()
        st.metric("📉 Variabilidad del Consumo", f"{variability:.2%}",
                 help="Coeficiente de variación - valores altos indican inestabilidad")

        # Costo estimado
        costo_kwh = st.number_input("💰 Costo por kWh (opcional):", min_value=0.0, value=2.5, step=0.5)
        costo_total = energia_total * costo_kwh
        st.metric("💵 Costo Estimado", f"${costo_total:,.2f} MXN")

    with col_rec3:
        # Picos por hora
        peak_hours = df_filtered.groupby('Hora')['kW_Instant'].max().nlargest(3)
        st.write("⏰ **Horas de Mayor Demanda:**")
        for hour, value in peak_hours.items():
            st.write(f"- {hour:02d}:00 → {value:.1f} kW")

        # Energía total
        st.metric("🔋 Energía Total", f"{energia_total:.2f} kWh")

else:
    st.info("🚀 **Esperando archivo...** Sube el CSV/Excel del HOBO para empezar el análisis industrial.")
    st.markdown("""
    ### ⚡ Características del Analizador Industrial:
    - **Conversión automática de Amperios a kW** con selección de voltaje (480V/220V/110V)
    - **Detección automática de picos de demanda** con umbral personalizable
    - **Cálculo de energía total** (kWh) mediante integración numérica
    - **Análisis por turnos** (1, 2, 3) con comparativas
    - **Tabla pivote interactiva** con drill-down por hora/día/turno
    - **Visualización profesional** con hovers mejorados
    - **Recomendaciones automáticas** de eficiencia energética
    - **Compatibilidad con formato HOBO** (archivos con estructura especial)
    - **Gráfica de tendencia con Altair** para visualizar consumo promedio por hora

    ### 📐 Fórmulas aplicadas:
    - **kW = (V × I × PF × √3) / 1000** (Sistema trifásico)
    - **Energía (kWh) = ∫ P(t) dt** (Regla del Trapecio)
    """)