"""Página: Dashboard Nacional consolidado.

Muestra agregaciones país y comparativas año a año en los 3 escenarios.
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
from src.ui_components import (  # noqa: E402
    kpi_con_fuente, leyenda_niveles, popover_origen_chart,
)
from src.utils import formato_numero_argentino, formato_porcentaje  # noqa: E402

st.set_page_config(page_title="ARCION · Dashboard Nacional", page_icon="📊", layout="wide")
st.title("📊 ARCION · Dashboard Nacional")

# Mapa de colores compartido entre tabla y charts
COLORES_ESCENARIO = {
    "historico": "#374151",
    "pesimista": "#DC2626",
    "base":      "#2563EB",
    "optimista": "#16A34A",
}


@st.cache_data
def cargar() -> tuple[pd.DataFrame, pd.DataFrame]:
    df_proy = pd.read_csv(config.ARCHIVO_PROYECCION_CSV, encoding="utf-8-sig")
    df_nac = pd.read_csv(config.ARCHIVO_RESUMEN_NACIONAL, encoding="utf-8-sig")
    return df_proy, df_nac


df_proy, df_nac = cargar()

# ---------------------------------------------------------------------
# Tabla resumen por año / escenario
# ---------------------------------------------------------------------
st.subheader("📋 Resumen anual por escenario")
col_pop_tabla, _ = st.columns([2, 5])
with col_pop_tabla:
    popover_origen_chart(
        "Origen de los datos",
        ["Tasa_Nacional_Actual", "Tasa_Nacional_Proyectada",
         "Población_Total", "OMS_Optimo"],
    )

# Filtros
escenarios_disponibles = df_nac["Escenario"].unique().tolist()
col_f1, col_f2 = st.columns([2, 5])
with col_f1:
    escenarios_filtro = st.multiselect(
        "Filtrar escenarios:",
        options=escenarios_disponibles,
        default=escenarios_disponibles,
        key="filtro_escenario_dashnac",
    )
if not escenarios_filtro:
    st.info("Seleccioná al menos un escenario para ver la tabla.")
else:
    df_filtrado = df_nac[df_nac["Escenario"].isin(escenarios_filtro)].copy()

    df_show = df_filtrado.copy()
    df_show["Año"] = df_show["Año"].astype(str)  # evita "2,025"
    df_show["Población_Total"] = df_show["Población_Total"].apply(
        lambda v: formato_numero_argentino(v, 0)
    )
    df_show["Tasa_Nacional_x1000"] = df_show["Tasa_Nacional_x1000"].apply(
        lambda v: formato_numero_argentino(v, 2)
    )
    df_show["Donantes_Anuales"] = df_show["Donantes_Anuales"].apply(
        lambda v: formato_numero_argentino(v, 0)
    )
    df_show["Donantes_OMS_Necesarios"] = df_show["Donantes_OMS_Necesarios"].apply(
        lambda v: formato_numero_argentino(v, 0)
    )
    df_show["Brecha_Donantes"] = df_show["Brecha_Donantes"].apply(
        lambda v: formato_numero_argentino(v, 0)
    )
    df_show["Pct_Cumplimiento_OMS"] = df_show["Pct_Cumplimiento_OMS"].apply(
        lambda v: f"{formato_numero_argentino(v, 1)}%"
    )

    def _color_escenario(val: str) -> str:
        color = COLORES_ESCENARIO.get(val)
        if color:
            return f"background-color: {color}; color: white; font-weight: 600;"
        return ""

    cols_numericas = [
        "Población_Total", "Donantes_Anuales", "Donantes_OMS_Necesarios",
        "Tasa_Nacional_x1000", "Brecha_Donantes", "Pct_Cumplimiento_OMS",
    ]
    styled = (
        df_show.style
        .map(_color_escenario, subset=["Escenario"])
        .set_properties(subset=cols_numericas, **{"text-align": "right"})
        .set_properties(subset=["Año"], **{"text-align": "center"})
    )
    st.dataframe(styled, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------
# Donantes anuales por escenario (con puente histórico → 2025)
# ---------------------------------------------------------------------
st.subheader("💉 Donantes anuales — comparación por escenario")
col_pop_donantes, _ = st.columns([2, 5])
with col_pop_donantes:
    popover_origen_chart(
        "Origen de los datos",
        ["Tasa_Nacional_Actual", "Tasa_Nacional_Proyectada", "Población_Total"],
    )

# Punto puente: último valor histórico, lo prependemos a cada escenario
# para que se vea continuidad y se distinga claramente que 2025 es el
# primer año de proyección (los 3 escenarios convergen ahí).
fila_puente_d = df_nac[
    (df_nac["Escenario"] == "historico") &
    (df_nac["Año"] == config.ANIO_FIN_HISTORICO)
].head(1)
puente_x_d = (
    int(fila_puente_d["Año"].iloc[0]) if not fila_puente_d.empty else None
)
puente_y_d = (
    float(fila_puente_d["Donantes_Anuales"].iloc[0])
    if not fila_puente_d.empty else None
)

fig_donantes = go.Figure()
for esc, color in COLORES_ESCENARIO.items():
    sub = df_nac[df_nac["Escenario"] == esc].sort_values("Año")
    if sub.empty:
        continue
    x_vals = sub["Año"].tolist()
    y_vals = sub["Donantes_Anuales"].tolist()
    if esc != "historico" and puente_x_d is not None:
        x_vals = [puente_x_d] + x_vals
        y_vals = [puente_y_d] + y_vals
    fig_donantes.add_trace(go.Scatter(
        x=x_vals, y=y_vals, mode="lines+markers", name=esc.capitalize(),
        line=dict(color=color, width=3),
    ))
fig_donantes.add_vrect(
    x0=config.ANIO_FIN_HISTORICO + 0.5,
    x1=config.ANIO_FIN_PROYECCION + 0.5,
    fillcolor="#FCD34D", opacity=0.10, line_width=0,
    annotation_text="Proyección", annotation_position="top left",
)
fig_donantes.update_layout(
    template="plotly_white", hovermode="x unified", height=450,
    xaxis_title="Año", yaxis_title="Cantidad de donantes",
    legend_title="Escenario",
)
st.plotly_chart(fig_donantes, use_container_width=True)

# ---------------------------------------------------------------------
# Brecha vs OMS (apilado)
# ---------------------------------------------------------------------
st.subheader("⚠️ Brecha contra meta OMS")
col_pop_brecha, _ = st.columns([2, 5])
with col_pop_brecha:
    popover_origen_chart(
        "Origen de los datos",
        ["Brecha_Donantes_OMS", "Donantes_Anuales", "OMS_Optimo"],
    )

df_brecha = df_nac[df_nac["Año"] >= config.ANIO_INICIO_HISTORICO].copy()
fig_brecha = px.bar(
    df_brecha[df_brecha["Escenario"].isin(["historico", "base"])],
    x="Año", y="Brecha_Donantes", color="Escenario", barmode="group",
    color_discrete_map={"historico": "#374151", "base": "#2563EB"},
    labels={"Brecha_Donantes": "Donantes faltantes vs OMS"},
)
fig_brecha.update_layout(template="plotly_white", height=420)
st.plotly_chart(fig_brecha, use_container_width=True)

# ---------------------------------------------------------------------
# Variación interanual de la tasa nacional
# ---------------------------------------------------------------------
st.subheader("🔄 Variación interanual (escenario base)")

df_base = df_nac[df_nac["Escenario"].isin(["historico", "base"])].sort_values("Año").copy()
df_base["Var_Tasa"] = df_base["Tasa_Nacional_x1000"].diff().round(2)

leyenda_niveles()
c1, c2 = st.columns(2)
with c1:
    kpi_con_fuente(
        label="Variación promedio histórica",
        value=formato_numero_argentino(
            df_base[df_base["Escenario"] == "historico"]["Var_Tasa"].mean(), 2
        ) + " /año",
        fuente_key="Variacion_Tasa_Historica",
    )
with c2:
    kpi_con_fuente(
        label="Variación promedio proyectada (base)",
        value=formato_numero_argentino(
            df_base[df_base["Escenario"] == "base"]["Var_Tasa"].mean(), 2
        ) + " /año",
        fuente_key="Variacion_Tasa_Proyectada",
    )

fig_var = go.Figure()
fig_var.add_trace(go.Bar(
    x=df_base["Año"], y=df_base["Var_Tasa"],
    marker_color=df_base["Var_Tasa"].apply(
        lambda v: "#16A34A" if v > 0 else "#DC2626"
    ),
))
fig_var.update_layout(
    xaxis_title="Año",
    yaxis_title="Δ Tasa (por 1000 hab)",
    template="plotly_white", height=380,
)
st.plotly_chart(fig_var, use_container_width=True)
