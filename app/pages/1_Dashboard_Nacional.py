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
from src.ui_components import kpi_con_fuente, leyenda_niveles  # noqa: E402
from src.utils import formato_numero_argentino, formato_porcentaje  # noqa: E402

st.set_page_config(page_title="ARCION · Dashboard Nacional", page_icon="🇦🇷", layout="wide")
st.title("🇦🇷 ARCION · Dashboard Nacional")


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
df_show = df_nac.copy()
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
st.dataframe(df_show, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------
# Donantes acumulados por escenario
# ---------------------------------------------------------------------
st.subheader("💉 Donantes anuales — comparación por escenario")

fig_donantes = px.line(
    df_nac, x="Año", y="Donantes_Anuales", color="Escenario",
    markers=True,
    color_discrete_map={
        "historico": "#374151", "pesimista": "#DC2626",
        "base": "#2563EB", "optimista": "#16A34A",
    },
    labels={"Donantes_Anuales": "Cantidad de donantes", "Año": "Año"},
)
fig_donantes.update_layout(template="plotly_white", hovermode="x unified", height=450)
st.plotly_chart(fig_donantes, use_container_width=True)

# ---------------------------------------------------------------------
# Brecha vs OMS (apilado)
# ---------------------------------------------------------------------
st.subheader("⚠️ Brecha contra meta OMS")

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
