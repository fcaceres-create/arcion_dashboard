"""Aplicación Streamlit principal del proyecto.

Página de inicio con KPIs nacionales, gráfico de escenarios y mapa
coroplético. Las páginas adicionales viven en ``app/pages/``.

Para ejecutar:
    $ streamlit run app/Inicio.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Permite importar desde src cuando se corre la app
RUTA_RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RUTA_RAIZ))

from src import config  # noqa: E402
from src.ui_components import (  # noqa: E402
    kpi_con_fuente, leyenda_niveles, popover_origen_chart,
)
from src.utils import formato_numero_argentino, formato_porcentaje  # noqa: E402

# ---------------------------------------------------------------------
# Configuración de página
# ---------------------------------------------------------------------
st.set_page_config(
    page_title="ARCION · Donantes Argentina 2030",
    page_icon="🩸",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------------
# Carga de datos (con autoejecución del pipeline si no existen)
# ---------------------------------------------------------------------
@st.cache_data(show_spinner="Cargando proyecciones...")
def cargar_datos() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Carga el CSV de proyección. Si no existe, ejecuta el pipeline.

    Returns:
        Tupla ``(df_proyeccion, df_resumen_nacional)``.
    """
    if not config.ARCHIVO_PROYECCION_CSV.exists():
        st.warning("No se encontraron resultados. Ejecutando pipeline...")
        from scripts.run_pipeline import ejecutar_pipeline
        ejecutar_pipeline()
    df_proy = pd.read_csv(config.ARCHIVO_PROYECCION_CSV, encoding="utf-8-sig")
    df_nac = pd.read_csv(config.ARCHIVO_RESUMEN_NACIONAL, encoding="utf-8-sig")
    return df_proy, df_nac


# ---------------------------------------------------------------------
# Header y descripción
# ---------------------------------------------------------------------
st.title("🩸 ARCION · Proyección de Donantes de Sangre 2030")
st.caption("Argentina · 24 jurisdicciones · Comparativa OMS 30/1.000 hab")
st.markdown(
    """
    **ARCION** es la aplicación de análisis predictivo desarrollada en el
    marco de un **trabajo de tesis** que proyecta la cantidad de donantes
    voluntarios de sangre en las **24 jurisdicciones argentinas** hasta
    2030 y la compara contra el **óptimo recomendado por la OMS**
    (30 donaciones / 1.000 habitantes).
    """
)

with st.expander("ℹ️ Sobre los datos"):
    st.info(
        "Esta versión utiliza un **dataset sintético** calibrado a la línea "
        "base nacional (~19/1000, OPS 2023). Se reemplazará por datos "
        "oficiales del Plan Nacional de Sangre cuando estén disponibles."
    )

df_proy, df_nac = cargar_datos()

# ---------------------------------------------------------------------
# Sidebar: filtros globales
# ---------------------------------------------------------------------
st.sidebar.header("⚙️ Filtros")
escenario_seleccionado = st.sidebar.selectbox(
    "Escenario para los KPIs:",
    options=list(config.ESCENARIOS),
    index=1,  # base
)
st.sidebar.caption(
    "Pesimista, Base y Optimista difieren en supuestos de campañas, "
    "desempleo, educación y centros."
)

# ---------------------------------------------------------------------
# KPIs nacionales
# ---------------------------------------------------------------------
st.subheader("📊 KPIs nacionales")
leyenda_niveles()

# Tasa actual (último año histórico)
fila_actual = df_nac[
    (df_nac["Escenario"] == "historico") &
    (df_nac["Año"] == config.ANIO_FIN_HISTORICO)
]
if fila_actual.empty:
    # Si no hay 'historico' en el resumen, tomo el último de cualquier escenario
    fila_actual = df_nac[df_nac["Año"] == config.ANIO_FIN_HISTORICO].head(1)

tasa_actual = float(fila_actual["Tasa_Nacional_x1000"].iloc[0]) if len(fila_actual) else config.TASA_ARGENTINA_BASE

# Tasa proyectada 2030 según escenario
fila_2030 = df_nac[
    (df_nac["Escenario"] == escenario_seleccionado) &
    (df_nac["Año"] == config.ANIO_FIN_PROYECCION)
]
tasa_2030 = float(fila_2030["Tasa_Nacional_x1000"].iloc[0]) if len(fila_2030) else 0.0
brecha_oms = config.OMS_OPTIMO_X1000 - tasa_2030
cumplimiento = tasa_2030 / config.OMS_OPTIMO_X1000

c1, c2, c3, c4 = st.columns(4)
with c1:
    kpi_con_fuente(
        label=f"Tasa actual ({config.ANIO_FIN_HISTORICO})",
        value=f"{formato_numero_argentino(tasa_actual, 2)} / 1000",
        fuente_key="Tasa_Nacional_Actual",
    )
with c2:
    kpi_con_fuente(
        label=f"Proyección {config.ANIO_FIN_PROYECCION}",
        value=f"{formato_numero_argentino(tasa_2030, 2)} / 1000",
        delta=f"{formato_numero_argentino(tasa_2030 - tasa_actual, 2)}",
        fuente_key="Tasa_Nacional_Proyectada",
    )
with c3:
    kpi_con_fuente(
        label="Brecha OMS",
        value=f"{formato_numero_argentino(brecha_oms, 2)} / 1000",
        delta_color="inverse",
        fuente_key="Brecha_OMS",
    )
with c4:
    kpi_con_fuente(
        label="% cumplimiento OMS",
        value=formato_porcentaje(cumplimiento, 1),
        fuente_key="Pct_Cumplimiento_OMS",
    )

# ---------------------------------------------------------------------
# Gráfico de escenarios + línea OMS
# ---------------------------------------------------------------------
st.subheader("📈 Trayectoria nacional · 3 escenarios vs meta OMS")
col_t_pop, _ = st.columns([2, 5])
with col_t_pop:
    popover_origen_chart(
        "Origen de los datos",
        ["Tasa_Nacional_Actual", "Tasa_Nacional_Proyectada", "OMS_Optimo"],
    )

df_plot = df_nac.copy()
fig_lineas = go.Figure()
colores = {"historico": "#374151", "pesimista": "#DC2626",
            "base": "#2563EB", "optimista": "#16A34A"}

# Punto puente: último valor histórico, lo prependemos a cada escenario
# para que se vea la continuidad visual entre el histórico y el inicio
# de la proyección (2025) sin "ruptura".
fila_puente = df_plot[
    (df_plot["Escenario"] == "historico") &
    (df_plot["Año"] == config.ANIO_FIN_HISTORICO)
].head(1)
puente_x = int(fila_puente["Año"].iloc[0]) if not fila_puente.empty else None
puente_y = float(fila_puente["Tasa_Nacional_x1000"].iloc[0]) if not fila_puente.empty else None

for esc, color in colores.items():
    sub = df_plot[df_plot["Escenario"] == esc].sort_values("Año")
    if sub.empty:
        continue
    x_vals = sub["Año"].tolist()
    y_vals = sub["Tasa_Nacional_x1000"].tolist()
    if esc != "historico" and puente_x is not None:
        x_vals = [puente_x] + x_vals
        y_vals = [puente_y] + y_vals
    fig_lineas.add_trace(go.Scatter(
        x=x_vals, y=y_vals,
        mode="lines+markers", name=esc.capitalize(),
        line=dict(color=color, width=3),
    ))

# Banda de proyección para distinguir visualmente histórico vs futuro
fig_lineas.add_vrect(
    x0=config.ANIO_FIN_HISTORICO + 0.5,
    x1=config.ANIO_FIN_PROYECCION + 0.5,
    fillcolor="#FCD34D", opacity=0.10, line_width=0,
    annotation_text="Proyección", annotation_position="top left",
)

fig_lineas.add_hline(
    y=config.OMS_OPTIMO_X1000, line_dash="dash", line_color="#B45309",
    annotation_text=f"Meta OMS: {config.OMS_OPTIMO_X1000}/1000",
    annotation_position="top left",
)
fig_lineas.update_layout(
    xaxis_title="Año",
    yaxis_title="Donaciones por 1000 habitantes",
    legend_title="Escenario",
    hovermode="x unified",
    template="plotly_white",
    height=480,
)
st.plotly_chart(fig_lineas, use_container_width=True)

# ---------------------------------------------------------------------
# Mapa coroplético
# ---------------------------------------------------------------------
st.subheader(
    f"🗺️ Mapa provincial · {config.ANIO_FIN_PROYECCION} · "
    f"Escenario {escenario_seleccionado}"
)
col_m_pop, _ = st.columns([2, 5])
with col_m_pop:
    popover_origen_chart(
        "Origen de los datos",
        ["Tasa_Donacion_x1000", "OMS_Optimo"],
    )

df_mapa = df_proy[
    (df_proy["Escenario"] == escenario_seleccionado) &
    (df_proy["Año"] == config.ANIO_FIN_PROYECCION)
].copy()

# Como GeoJSON oficial puede no estar embebido, usamos un mapa horizontal por barras
# (gráfico tipo treemap como alternativa visual).
fig_mapa = px.bar(
    df_mapa.sort_values("Tasa_Donacion_x1000", ascending=True),
    x="Tasa_Donacion_x1000",
    y="Provincia",
    color="Tasa_Donacion_x1000",
    color_continuous_scale="RdYlGn",
    range_color=(10, 30),
    labels={
        "Tasa_Donacion_x1000": "Donaciones por 1000 hab",
        "Provincia": "Jurisdicción",
    },
    height=720,
    orientation="h",
)
fig_mapa.add_vline(
    x=config.OMS_OPTIMO_X1000, line_dash="dash", line_color="black",
    annotation_text="Meta OMS",
)
fig_mapa.update_layout(template="plotly_white")
st.plotly_chart(fig_mapa, use_container_width=True)

st.caption(
    "💡 Para drill-down por provincia, simulación de escenarios y "
    "explicación metodológica, navegá a las páginas del menú lateral."
)

# ---------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------
st.markdown("---")
st.markdown(
    f"**ARCION** · Proyecto de Tesis · "
    f"**Autora:** Gisela Poliak · "
    f"Datos: INDEC, OPS, Min. Salud (REFES, Vigilancia, Estadísticas Vitales) · "
    f"Modelo: ML supervisado"
)
