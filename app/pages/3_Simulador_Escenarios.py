"""Página: Simulador interactivo de escenarios.

Permite al usuario modificar variables clave (campañas, educación,
centros, desempleo, dengue) mediante sliders y observar en tiempo
real cómo cambia la proyección 2030 a nivel provincial.

La predicción usa el último modelo entrenado, leyendo sus métricas
desde ``data/output/model_metrics.json``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

RUTA_RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RUTA_RAIZ))

from src import config  # noqa: E402
from src.data_loader import cargar_dataset_maestro  # noqa: E402
from src.feature_engineering import (  # noqa: E402
    construir_features, obtener_columnas_modelo,
)
from src.model import entrenar_y_seleccionar  # noqa: E402
from src.projection import proyectar_features_completo  # noqa: E402
from src.utils import formato_numero_argentino  # noqa: E402

st.set_page_config(page_title="Simulador", page_icon="🎛️", layout="wide")
st.title("🎛️ Simulador de escenarios")

st.markdown(
    """
    Modificá las variables predictoras con los sliders para ver cómo
    impactan en la **proyección de la tasa de donación al 2030**.
    El modelo recalcula la predicción en tiempo real.
    """
)


# ---------------------------------------------------------------------
# Carga + entrenamiento (cacheado)
# ---------------------------------------------------------------------
@st.cache_resource(show_spinner="Entrenando modelo...")
def preparar_modelo():
    df_maestro = cargar_dataset_maestro()
    df_hist = df_maestro[df_maestro["Año"] <= config.ANIO_FIN_HISTORICO].copy()
    df_features = construir_features(df_hist)
    resultado = entrenar_y_seleccionar(df_features, guardar_metricas=False)
    df_panel = proyectar_features_completo(df_hist)
    df_panel_features = construir_features(df_panel)
    return resultado, df_panel_features


resultado, df_panel = preparar_modelo()
modelo = resultado.modelo_mejor
columnas_modelo = resultado.columnas_features

st.info(f"Modelo activo: **{resultado.nombre_mejor}** "
        f"(MAE-CV = {resultado.metricas[resultado.nombre_mejor].mae_cv:.3f})")

# ---------------------------------------------------------------------
# Selección de provincia
# ---------------------------------------------------------------------
provincia = st.selectbox(
    "Jurisdicción a simular:",
    sorted(df_panel["Provincia"].unique().tolist()),
)

# Estado base (año 2030 sin ajustes)
fila_base = df_panel[
    (df_panel["Provincia"] == provincia) &
    (df_panel["Año"] == config.ANIO_FIN_PROYECCION)
].copy()
if fila_base.empty:
    st.error(f"No hay datos proyectados para {provincia} en {config.ANIO_FIN_PROYECCION}.")
    st.stop()

# ---------------------------------------------------------------------
# Sliders
# ---------------------------------------------------------------------
st.subheader("⚙️ Variables ajustables")

col1, col2 = st.columns(2)
with col1:
    delta_campañas = st.slider(
        "Cambio en campañas anuales (%)",
        min_value=-50, max_value=100, value=0, step=5,
    )
    delta_educacion = st.slider(
        "Cambio en % educación superior (puntos pp)",
        min_value=-10, max_value=15, value=0, step=1,
    )
    delta_desempleo = st.slider(
        "Cambio en tasa de desempleo (puntos pp)",
        min_value=-5, max_value=10, value=0, step=1,
    )

with col2:
    delta_centros = st.slider(
        "Cambio en centros de hemoterapia (%)",
        min_value=-30, max_value=80, value=0, step=5,
    )
    delta_cobertura = st.slider(
        "Cambio en % cobertura de salud (puntos pp)",
        min_value=-10, max_value=15, value=0, step=1,
    )
    delta_dengue = st.slider(
        "Cambio en casos de dengue (%)",
        min_value=-50, max_value=200, value=0, step=10,
    )

# ---------------------------------------------------------------------
# Aplicar ajustes y predecir
# ---------------------------------------------------------------------
# Partimos de la fila YA featurizada (incluye lag, dummies de región, etc.)
# y modificamos in-place solo lo que cambia con los sliders. Reconstruir
# features sobre una sola provincia rompería el one-hot encoding de Region.
fila_ajustada = fila_base.copy()
fila_ajustada["Campañas_Donacion_Anuales"] = (
    fila_ajustada["Campañas_Donacion_Anuales"] * (1 + delta_campañas / 100)
).round()
fila_ajustada["Pct_Educacion_Superior"] += delta_educacion
fila_ajustada["Tasa_Desempleo"] += delta_desempleo
fila_ajustada["Centros_Hemoterapia"] = (
    fila_ajustada["Centros_Hemoterapia"] * (1 + delta_centros / 100)
).round()
fila_ajustada["Pct_Cobertura_Salud"] = np.clip(
    fila_ajustada["Pct_Cobertura_Salud"] + delta_cobertura, 35, 99
)
fila_ajustada["Casos_Dengue_Anual"] = (
    fila_ajustada["Casos_Dengue_Anual"] * (1 + delta_dengue / 100)
).clip(0).round()

# Recalculamos SOLO las features derivadas que dependen de variables modificadas.
poblacion = fila_ajustada["Población_Total"]
fila_ajustada["Centros_x_100k_hab"] = (
    fila_ajustada["Centros_Hemoterapia"] / poblacion * 100_000
).round(3)
fila_ajustada["Campañas_per_capita"] = (
    fila_ajustada["Campañas_Donacion_Anuales"] / poblacion * 100_000
).round(3)
fila_ajustada["Casos_Dengue_x_1000_hab"] = (
    fila_ajustada["Casos_Dengue_Anual"] / poblacion * 1000
).round(3)

X_sim = fila_ajustada[columnas_modelo]
prediccion_simulada = float(np.clip(modelo.predict(X_sim)[0], 5, 40))

# Predicción base (sin ajustes): la fila base ya viene featurizada
X_base = fila_base[columnas_modelo]
prediccion_base = float(np.clip(modelo.predict(X_base)[0], 5, 40))

# ---------------------------------------------------------------------
# Resultados
# ---------------------------------------------------------------------
st.subheader(f"📊 Resultados para {provincia} · {config.ANIO_FIN_PROYECCION}")

c1, c2, c3 = st.columns(3)
c1.metric(
    "Tasa proyectada (base)",
    f"{formato_numero_argentino(prediccion_base, 2)} /1000",
)
c2.metric(
    "Tasa simulada",
    f"{formato_numero_argentino(prediccion_simulada, 2)} /1000",
    f"{formato_numero_argentino(prediccion_simulada - prediccion_base, 2)}",
)
c3.metric(
    "% cumplimiento OMS",
    f"{formato_numero_argentino(prediccion_simulada / config.OMS_OPTIMO_X1000 * 100, 1)}%",
)

# Gráfico comparativo
poblacion = float(fila_ajustada["Población_Total"].iloc[0])
donantes_base_abs = prediccion_base * poblacion / 1000
donantes_sim_abs = prediccion_simulada * poblacion / 1000
donantes_oms = config.OMS_OPTIMO_X1000 * poblacion / 1000

fig = go.Figure()
fig.add_trace(go.Bar(
    x=["Proyección base", "Simulación", "Meta OMS"],
    y=[donantes_base_abs, donantes_sim_abs, donantes_oms],
    marker_color=["#2563EB", "#16A34A", "#B45309"],
    text=[formato_numero_argentino(v, 0) for v in
            [donantes_base_abs, donantes_sim_abs, donantes_oms]],
    textposition="outside",
))
fig.update_layout(
    title=f"Donantes proyectados {config.ANIO_FIN_PROYECCION} · {provincia}",
    yaxis_title="Cantidad de donantes",
    template="plotly_white", height=420,
)
st.plotly_chart(fig, use_container_width=True)

st.caption(
    "💡 La predicción se actualiza automáticamente al mover los sliders. "
    "El modelo subyacente fue seleccionado por validación cruzada k=5."
)
