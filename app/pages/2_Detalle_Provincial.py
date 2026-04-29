"""Página: Detalle Provincial.

Drill-down por jurisdicción: trayectoria de la tasa, donantes
absolutos, brecha vs OMS, ranking y comparativa regional.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

RUTA_RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RUTA_RAIZ))

from src import config  # noqa: E402
from src.utils import formato_numero_argentino, formato_porcentaje  # noqa: E402

st.set_page_config(page_title="ARCION · Detalle Provincial", page_icon="📍", layout="wide")
st.title("📍 ARCION · Detalle Provincial")


@st.cache_data
def cargar() -> pd.DataFrame:
    return pd.read_csv(config.ARCHIVO_PROYECCION_CSV, encoding="utf-8-sig")


df = cargar()

# ---------------------------------------------------------------------
# Selección de provincia y escenario
# ---------------------------------------------------------------------
provincias = sorted(df["Provincia"].unique().tolist())
col_a, col_b = st.columns([2, 1])
provincia_sel = col_a.selectbox("Jurisdicción:", provincias)
escenario_sel = col_b.selectbox("Escenario:", list(config.ESCENARIOS), index=1)

df_prov = df[df["Provincia"] == provincia_sel].copy()
df_serie = df_prov[
    (df_prov["Escenario"] == "historico") |
    (df_prov["Escenario"] == escenario_sel)
].sort_values("Año")

# ---------------------------------------------------------------------
# KPIs provinciales
# ---------------------------------------------------------------------
fila_actual = df_serie[df_serie["Año"] == config.ANIO_FIN_HISTORICO].head(1)
fila_2030 = df_serie[df_serie["Año"] == config.ANIO_FIN_PROYECCION].head(1)

if not fila_actual.empty and not fila_2030.empty:
    tasa_act = float(fila_actual["Tasa_Donacion_x1000"].iloc[0])
    tasa_30 = float(fila_2030["Tasa_Donacion_x1000"].iloc[0])
    donantes_30 = int(fila_2030["Donantes_Anuales"].iloc[0])
    brecha_30 = int(fila_2030["Brecha_Donantes"].iloc[0])

    c1, c2, c3, c4 = st.columns(4)
    c1.metric(f"Tasa {config.ANIO_FIN_HISTORICO}",
              f"{formato_numero_argentino(tasa_act, 2)} /1000")
    c2.metric(f"Tasa {config.ANIO_FIN_PROYECCION}",
              f"{formato_numero_argentino(tasa_30, 2)} /1000",
              f"{formato_numero_argentino(tasa_30 - tasa_act, 2)}")
    c3.metric(f"Donantes {config.ANIO_FIN_PROYECCION}",
              formato_numero_argentino(donantes_30, 0))
    c4.metric("Brecha vs OMS",
              formato_numero_argentino(brecha_30, 0),
              delta_color="inverse")

st.markdown(f"**Región:** {df_prov['Region'].iloc[0]}")

# ---------------------------------------------------------------------
# Trayectoria de la tasa
# ---------------------------------------------------------------------
st.subheader("📈 Trayectoria de la tasa de donación")

fig = go.Figure()
fig.add_trace(go.Scatter(
    x=df_serie["Año"], y=df_serie["Tasa_Donacion_x1000"],
    mode="lines+markers", name="Tasa observada/proyectada",
    line=dict(color="#2563EB", width=3),
))
fig.add_hline(
    y=config.OMS_OPTIMO_X1000, line_dash="dash", line_color="#B45309",
    annotation_text=f"Meta OMS: {config.OMS_OPTIMO_X1000}/1000",
)
fig.add_vrect(
    x0=config.ANIO_FIN_HISTORICO + 0.5,
    x1=config.ANIO_FIN_PROYECCION + 0.5,
    fillcolor="#FCD34D", opacity=0.2, line_width=0,
    annotation_text="Proyección", annotation_position="top left",
)
fig.update_layout(template="plotly_white", height=440,
                  xaxis_title="Año", yaxis_title="Donaciones / 1000 hab")
st.plotly_chart(fig, use_container_width=True)

# ---------------------------------------------------------------------
# Donantes absolutos vs necesarios OMS
# ---------------------------------------------------------------------
st.subheader("💉 Donantes anuales vs requerimiento OMS")

fig_d = go.Figure()
fig_d.add_trace(go.Bar(
    x=df_serie["Año"], y=df_serie["Donantes_Anuales"],
    name="Donantes esperados", marker_color="#2563EB",
))
fig_d.add_trace(go.Scatter(
    x=df_serie["Año"], y=df_serie["Donantes_OMS_Necesarios"],
    name="Necesarios (OMS)", mode="lines+markers",
    line=dict(color="#B45309", dash="dash"),
))
fig_d.update_layout(template="plotly_white", height=420, barmode="overlay",
                     xaxis_title="Año", yaxis_title="Cantidad de donantes")
st.plotly_chart(fig_d, use_container_width=True)

# ---------------------------------------------------------------------
# Ranking provincial 2030
# ---------------------------------------------------------------------
st.subheader(f"🏆 Ranking de provincias · {config.ANIO_FIN_PROYECCION}")

df_rank = df[
    (df["Año"] == config.ANIO_FIN_PROYECCION) &
    (df["Escenario"] == escenario_sel)
].sort_values("Tasa_Donacion_x1000", ascending=False).reset_index(drop=True)
df_rank["Posición"] = df_rank.index + 1

# Resaltar provincia seleccionada
df_rank["__color"] = df_rank["Provincia"].apply(
    lambda p: "#DC2626" if p == provincia_sel else "#9CA3AF"
)

fig_rank = px.bar(
    df_rank,
    x="Tasa_Donacion_x1000",
    y="Provincia",
    orientation="h",
    height=720,
    color="__color",
    color_discrete_map={c: c for c in df_rank["__color"].unique()},
    labels={"Tasa_Donacion_x1000": "Tasa /1000"},
)
fig_rank.add_vline(x=config.OMS_OPTIMO_X1000, line_dash="dash", line_color="black")
fig_rank.update_layout(showlegend=False, template="plotly_white",
                        yaxis={"categoryorder": "total ascending"})
st.plotly_chart(fig_rank, use_container_width=True)

st.caption("La barra roja resalta la jurisdicción seleccionada.")
