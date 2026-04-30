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
from src.ui_components import kpi_con_fuente, leyenda_niveles  # noqa: E402
from src.utils import formato_numero_argentino  # noqa: E402

st.set_page_config(page_title="ARCION · Simulador", page_icon="🎛️", layout="wide")
st.title("🎛️ ARCION · Simulador de escenarios")

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

leyenda_niveles()
c1, c2, c3 = st.columns(3)
with c1:
    kpi_con_fuente(
        label="Tasa proyectada (base)",
        value=f"{formato_numero_argentino(prediccion_base, 2)} /1000",
        fuente_key="Tasa_Nacional_Proyectada",
    )
with c2:
    kpi_con_fuente(
        label="Tasa simulada",
        value=f"{formato_numero_argentino(prediccion_simulada, 2)} /1000",
        delta=f"{formato_numero_argentino(prediccion_simulada - prediccion_base, 2)}",
        fuente_key="Tasa_Simulada",
    )
with c3:
    kpi_con_fuente(
        label="% cumplimiento OMS",
        value=f"{formato_numero_argentino(prediccion_simulada / config.OMS_OPTIMO_X1000 * 100, 1)}%",
        fuente_key="Pct_Cumplimiento_OMS",
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

# ---------------------------------------------------------------------
# Historial de últimas N simulaciones
# ---------------------------------------------------------------------
HISTORIAL_KEY = "historial_simulador"
MAX_HISTORIAL = 5

if HISTORIAL_KEY not in st.session_state:
    st.session_state[HISTORIAL_KEY] = []

# Hash de la corrida actual para evitar duplicar entradas consecutivas
# cuando Streamlit re-ejecuta el script sin que el usuario haya tocado
# nada (p.ej. al cambiar de pestaña y volver).
hash_actual = (
    provincia, delta_campañas, delta_educacion, delta_desempleo,
    delta_centros, delta_cobertura, delta_dengue,
)
historial = st.session_state[HISTORIAL_KEY]
ultimo_hash = historial[-1].get("_hash") if historial else None

if hash_actual != ultimo_hash:
    historial.append({
        "_hash": hash_actual,
        "iter": (historial[-1]["iter"] + 1) if historial else 1,
        "Provincia": provincia,
        "Δ Camp.": f"{delta_campañas:+d}%",
        "Δ Educ.": f"{delta_educacion:+d} pp",
        "Δ Desempl.": f"{delta_desempleo:+d} pp",
        "Δ Centros": f"{delta_centros:+d}%",
        "Δ Cobert.": f"{delta_cobertura:+d} pp",
        "Δ Dengue": f"{delta_dengue:+d}%",
        "Tasa base": prediccion_base,
        "Tasa simulada": prediccion_simulada,
        "Δ tasa": prediccion_simulada - prediccion_base,
        "% OMS": prediccion_simulada / config.OMS_OPTIMO_X1000 * 100,
    })
    st.session_state[HISTORIAL_KEY] = historial[-MAX_HISTORIAL:]

historial_vivo = st.session_state[HISTORIAL_KEY]
if historial_vivo:
    st.markdown("---")
    cab1, cab2 = st.columns([5, 1])
    with cab1:
        st.subheader("📊 Comparación de tus últimas simulaciones")
        st.caption(
            f"Tus últimas {len(historial_vivo)} simulaciones únicas — "
            f"sirve para ver de un vistazo cómo cada ajuste de sliders "
            f"impactó la tasa proyectada. Se mantienen hasta {MAX_HISTORIAL} "
            f"y se descartan las más viejas automáticamente."
        )
    with cab2:
        if st.button("🗑️ Limpiar", key="limpiar_historial_sim"):
            st.session_state[HISTORIAL_KEY] = []
            st.rerun()

    df_hist = pd.DataFrame(historial_vivo).drop(columns=["_hash"])

    # --- Chart: barra de Δ tasa por iteración ---
    colores_barras = [
        "#16A34A" if d > 0 else ("#DC2626" if d < 0 else "#9CA3AF")
        for d in df_hist["Δ tasa"]
    ]
    fig_hist = go.Figure()
    fig_hist.add_trace(go.Bar(
        x=[f"#{i}" for i in df_hist["iter"]],
        y=df_hist["Δ tasa"],
        marker_color=colores_barras,
        text=[f"{d:+.2f}" for d in df_hist["Δ tasa"]],
        textposition="outside",
        hovertext=[
            f"{prov}<br>Tasa base: {b:.2f}<br>Tasa simulada: {s:.2f}"
            f"<br>% OMS: {p:.1f}%"
            for prov, b, s, p in zip(
                df_hist["Provincia"], df_hist["Tasa base"],
                df_hist["Tasa simulada"], df_hist["% OMS"],
            )
        ],
        hoverinfo="text",
    ))
    fig_hist.add_hline(y=0, line_color="#6B7280", line_width=1)
    fig_hist.update_layout(
        title="Δ Tasa simulada − Tasa base, por iteración",
        yaxis_title="Δ /1000 hab",
        xaxis_title="Iteración",
        template="plotly_white",
        height=320,
        showlegend=False,
        margin=dict(t=60, b=40),
    )
    st.plotly_chart(fig_hist, use_container_width=True)

    # --- Tabla detallada ---
    df_show_hist = df_hist.copy()
    df_show_hist["Tasa base"] = df_show_hist["Tasa base"].apply(
        lambda v: formato_numero_argentino(v, 2)
    )
    df_show_hist["Tasa simulada"] = df_show_hist["Tasa simulada"].apply(
        lambda v: formato_numero_argentino(v, 2)
    )
    df_show_hist["Δ tasa"] = df_show_hist["Δ tasa"].apply(
        lambda v: f"{v:+.2f}"
    )
    df_show_hist["% OMS"] = df_show_hist["% OMS"].apply(
        lambda v: f"{formato_numero_argentino(v, 1)}%"
    )
    df_show_hist = df_show_hist.rename(columns={"iter": "#"})
    df_show_hist = df_show_hist[[
        "#", "Provincia",
        "Δ Camp.", "Δ Educ.", "Δ Desempl.",
        "Δ Centros", "Δ Cobert.", "Δ Dengue",
        "Tasa base", "Tasa simulada", "Δ tasa", "% OMS",
    ]]

    def _color_delta_tasa(val: str) -> str:
        s = str(val).strip()
        if s.startswith("+") and s.lstrip("+").replace(",", ".") != "0.00":
            return "color: #16A34A; font-weight: 600;"
        if s.startswith("-"):
            return "color: #DC2626; font-weight: 600;"
        return "color: #6B7280;"

    cols_num_hist = ["Tasa base", "Tasa simulada", "Δ tasa", "% OMS"]
    styled_hist = (
        df_show_hist.style
        .map(_color_delta_tasa, subset=["Δ tasa"])
        .set_properties(subset=cols_num_hist, **{"text-align": "right"})
        .set_properties(subset=["#"], **{"text-align": "center"})
    )
    st.dataframe(styled_hist, use_container_width=True, hide_index=True)
