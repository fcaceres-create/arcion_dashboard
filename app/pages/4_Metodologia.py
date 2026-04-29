"""Página: Metodología.

Explicación pedagógica del modelo, las variables, las limitaciones y
las fuentes de datos. Pensada como complemento académico de la tesis.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

RUTA_RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RUTA_RAIZ))

from src import config  # noqa: E402

st.set_page_config(page_title="ARCION · Metodología", page_icon="📚", layout="wide")
st.title("📚 ARCION · Metodología")

st.markdown(
    """
    ## 1. Objetivo

    Proyectar la **tasa de donación voluntaria de sangre** y la **cantidad
    absoluta de donantes** en cada una de las 24 jurisdicciones argentinas
    al año 2030, comparando contra la meta de la OMS:

    > **30 donaciones / 1000 habitantes** — umbral asociado a autosuficiencia
    > hemoterápica según la *Organización Mundial de la Salud*.

    ## 2. Diseño del estudio

    - **Tipo:** estudio observacional retrospectivo con proyección prospectiva.
    - **Unidad de análisis:** jurisdicción (provincia / CABA) × año.
    - **Período histórico:** 2015–2024 (10 años, 240 observaciones).
    - **Período de proyección:** 2025–2030 (6 años, 144 puntos a estimar).

    ## 3. Variables

    El target es `Tasa_Donacion_x1000`. Las variables predictoras se
    agrupan en cuatro bloques:

    | Bloque | Variables |
    |--------|-----------|
    | Demográficas | Población total, población 18-65, densidad |
    | Socioeconómicas | % educación superior, índice de ingreso, tasa de desempleo, % cobertura de salud |
    | Sistema sanitario | Centros de hemoterapia, campañas de donación |
    | Epidemiológicas | Casos anuales de dengue |

    Adicionalmente, el módulo `feature_engineering` deriva ratios
    (centros/100k hab, campañas per cápita) y agrega una variable
    de memoria temporal (`Tasa_Donacion_Lag1`).

    ## 4. Modelo predictivo

    Se evalúan dos algoritmos de regresión basados en árboles, robustos
    frente a no linealidades y outliers:

    - **Random Forest Regressor** (200 árboles, profundidad máx. 12).
    - **Gradient Boosting Regressor** (300 etapas, learning rate 0.05).

    La selección se realiza por **validación cruzada K-Fold (k=5)** usando
    **MAE** como métrica primaria. Adicionalmente se reportan R² y RMSE
    sobre el conjunto de entrenamiento. La semilla aleatoria se fija a
    **42** para garantizar reproducibilidad.

    ## 5. Escenarios

    | Escenario | Supuestos |
    |-----------|-----------|
    | **Pesimista** | -15% campañas · +20% desempleo · +50% dengue |
    | **Base** | Predicción directa con extrapolación lineal de features |
    | **Optimista** | +50% campañas · +10% educación superior · +15% centros |

    ## 6. Limitaciones

    1. **Dataset sintético**: la versión actual usa datos generados
       artificialmente calibrados a la línea base nacional (~19/1000 OPS 2023).
       Será reemplazado por datos oficiales del **Plan Nacional de Sangre**.
    2. **Extrapolación**: las features futuras se proyectan linealmente,
       lo cual es una simplificación.
    3. **No considera shocks externos** (nuevas pandemias, cambios de política).
    4. **Granularidad provincial** uniforme; podría enriquecerse con datos
       por departamento si estuvieran disponibles.

    ## 7. Reproducibilidad

    - Código abierto en repositorio Git con commits versionados.
    - `requirements.txt` con versiones específicas.
    - Random state fijo (42) en todos los modelos.
    - Tests automatizados con `pytest`.
    """
)

# ---------------------------------------------------------------------
# Métricas del último entrenamiento (si están disponibles)
# ---------------------------------------------------------------------
st.subheader("📈 Métricas del último entrenamiento")

if config.ARCHIVO_METRICAS_MODELO.exists():
    with open(config.ARCHIVO_METRICAS_MODELO, "r", encoding="utf-8") as f:
        metricas = json.load(f)

    st.success(f"Modelo seleccionado: **{metricas['nombre_mejor']}**")

    filas = []
    for nombre, m in metricas["metricas"].items():
        filas.append({
            "Modelo": nombre,
            "MAE (CV)": round(m["mae_cv"], 4),
            "± Desvío": round(m["mae_cv_std"], 4),
            "R² (train)": round(m["r2_train"], 4),
            "RMSE (train)": round(m["rmse_train"], 4),
        })
    st.dataframe(pd.DataFrame(filas), hide_index=True, use_container_width=True)

    # Top 10 features más importantes
    importances = metricas["metricas"][metricas["nombre_mejor"]]["feature_importance"]
    top10 = dict(list(importances.items())[:10])
    df_imp = pd.DataFrame({
        "Feature": list(top10.keys()),
        "Importancia": list(top10.values()),
    }).sort_values("Importancia", ascending=True)

    fig = px.bar(
        df_imp, x="Importancia", y="Feature", orientation="h",
        color="Importancia", color_continuous_scale="Blues",
        height=400,
    )
    fig.update_layout(template="plotly_white",
                      title="Top 10 variables predictoras")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("Aún no hay métricas guardadas. Corré el pipeline primero.")

# ---------------------------------------------------------------------
# Fuentes
# ---------------------------------------------------------------------
st.subheader("📖 Fuentes de datos")
st.markdown(
    """
    - **OMS** — *Blood safety and availability*, 2023.
    - **OPS/PAHO** — *Suministro de sangre para transfusiones en países de
      Latinoamérica y el Caribe*, reporte 2023.
    - **INDEC** — Censo Nacional de Población, Hogares y Viviendas 2022;
      EPH (Encuesta Permanente de Hogares).
    - **Ministerio de Salud de la Nación Argentina** — Plan Nacional de Sangre,
      Boletín Integrado de Vigilancia.
    - **World Bank Open Data** — indicadores macroeconómicos y sanitarios.
    """
)
