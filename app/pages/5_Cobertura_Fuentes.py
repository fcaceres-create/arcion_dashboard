"""Página: Cobertura de fuentes oficiales.

Visualiza qué porcentaje de cada variable usa datos reales del Ministerio
de Salud (REFES, vigilancia epidemiológica, estadísticas vitales,
recursos humanos) vs el fallback sintético. Es clave para la defensa
académica: cualquier fila puede rastrearse a su fuente.

Para que esta página funcione, hay que correr previamente:

    python scripts/run_pipeline.py --fuentes-reales

(Genera ``data/output/cobertura_fuentes.csv``.)
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

RUTA_RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RUTA_RAIZ))

from src import config  # noqa: E402

st.set_page_config(page_title="ARCION · Cobertura de fuentes", page_icon="🔍",
                    layout="wide")
st.title("🔍 ARCION · Cobertura de fuentes oficiales")

st.markdown(
    """
    Esta página documenta la **trazabilidad académica** del dataset
    enriquecido. Cada variable predictora puede provenir de una fuente
    oficial del Ministerio de Salud o, cuando no hay cobertura, del
    valor sintético generado por el módulo `data_generator`.
    """
)

# ---------------------------------------------------------------------
# Carga del reporte
# ---------------------------------------------------------------------
RUTA_REPORTE = config.RUTA_DATA_OUTPUT / "cobertura_fuentes.csv"
RUTA_REFES_LEGACY = config.RUTA_DATA_OUTPUT / "cobertura_refes.csv"


@st.cache_data
def cargar_reporte() -> pd.DataFrame | None:
    if RUTA_REPORTE.exists():
        return pd.read_csv(RUTA_REPORTE, encoding="utf-8-sig")
    if RUTA_REFES_LEGACY.exists():
        return pd.read_csv(RUTA_REFES_LEGACY, encoding="utf-8-sig")
    return None


df = cargar_reporte()

if df is None:
    st.warning(
        "🟡 No hay reporte de cobertura todavía.\n\n"
        "Para generarlo, ejecutá en tu terminal:\n\n"
        "```bash\npython scripts/run_pipeline.py --fuentes-reales\n```\n\n"
        "El reporte se guarda en `data/output/cobertura_fuentes.csv` y se "
        "carga automáticamente acá."
    )
    st.stop()

# ---------------------------------------------------------------------
# KPIs globales
# ---------------------------------------------------------------------
es_completo = "Variable" in df.columns and "Fuente" in df.columns

if es_completo:
    total_filas = df["Filas"].sum()
    filas_reales = df.loc[df["Fuente"] != "sintetico", "Filas"].sum()
    pct_real_global = (
        filas_reales / total_filas * 100 if total_filas > 0 else 0
    )
    n_variables = df["Variable"].nunique()
    n_fuentes_reales = df.loc[df["Fuente"] != "sintetico", "Fuente"].nunique()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Variables enriquecidas", n_variables)
    c2.metric("Fuentes oficiales activas", n_fuentes_reales)
    c3.metric("Filas con dato real", f"{int(filas_reales):,}".replace(",", "."))
    c4.metric("Cobertura global real", f"{pct_real_global:.1f}%")

# ---------------------------------------------------------------------
# Visualización por variable
# ---------------------------------------------------------------------
st.subheader("📊 Cobertura por variable")

if es_completo:
    fig = px.bar(
        df.sort_values(["Variable", "Fuente"]),
        x="Pct", y="Variable",
        color="Fuente",
        orientation="h",
        text="Pct",
        labels={"Pct": "% del panel", "Variable": ""},
        color_discrete_map={
            "sintetico":         "#9CA3AF",
            "REFES":             "#2563EB",
            "Vigilancia_Dengue": "#DC2626",
            "VIH_MinSalud":      "#7C3AED",
            "MinSalud_RRHH":     "#16A34A",
            "EstVitales":        "#F59E0B",
        },
        height=500,
    )
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="inside")
    fig.update_layout(
        template="plotly_white",
        barmode="stack",
        xaxis_range=[0, 100],
        legend_title="Fuente",
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info(
        "Reporte legacy de REFES detectado. Para ver cobertura completa "
        "ejecutá el pipeline con `--fuentes-reales`."
    )
    st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------
# Tabla detallada
# ---------------------------------------------------------------------
st.subheader("📋 Detalle por fuente")
st.dataframe(df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------------
# Documentación de fuentes
# ---------------------------------------------------------------------
st.subheader("📖 Origen de cada fuente oficial")

st.markdown(
    """
| Fuente | Variables que aporta | Dataset oficial |
|--------|---------------------|-----------------|
| **REFES** | Centros de hemoterapia | `listado-establecimientos-de-salud-asentados-en-el-registro-federal-refes` |
| **Vigilancia Dengue** | Casos anuales de dengue | `vigilancia-de-dengue-y-zika` |
| **VIH MinSalud** | Casos anuales de VIH | `notificacion-de-casos-de-vih` |
| **MinSalud RRHH** | Cantidad de médicos | `profesionales-medicos-por-jurisdiccion` (DISCONTINUADO 2019) |
| **EstVitales** | Defunciones y nacimientos | `serie-historica-de-defunciones...` y `...-nacimientos...` |
| **sintetico** | Fallback calibrado | Generado por `src/data_generator.py` |

Todos los datasets se descargan vía el módulo
[`src/api_clients.py → DatosSaludArClient`](https://github.com/fcaceres-create/arcion_dashboard/blob/main/src/api_clients.py)
desde [datos.salud.gob.ar](https://datos.salud.gob.ar) con caché local.
"""
)

st.caption(
    "💡 La columna `Fuente_<Variable>` del dataset enriquecido permite "
    "filtrar/comparar resultados según el origen del dato."
)
