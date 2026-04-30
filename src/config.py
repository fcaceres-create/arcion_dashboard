"""Configuración global del proyecto.

Centraliza rutas, constantes del modelo, parámetros OMS y poblaciones
provinciales (basadas en el Censo INDEC 2022). Todas las constantes
deben importarse desde aquí; nunca hardcodear rutas en otros módulos.

Ejemplo de uso:
    >>> from src.config import RUTA_DATA_OUTPUT, OMS_OPTIMO_X1000
    >>> print(OMS_OPTIMO_X1000)
    30.0
"""
from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------
# Rutas del proyecto (siempre relativas a la raíz del repo)
# ---------------------------------------------------------------------
RUTA_RAIZ: Path = Path(__file__).resolve().parent.parent
RUTA_DATA: Path = RUTA_RAIZ / "data"
RUTA_DATA_RAW: Path = RUTA_DATA / "raw"
RUTA_DATA_PROCESSED: Path = RUTA_DATA / "processed"
RUTA_DATA_OUTPUT: Path = RUTA_DATA / "output"
RUTA_LOGS: Path = RUTA_RAIZ / "logs"
RUTA_API_CACHE: Path = RUTA_RAIZ / "src" / ".api_cache"

# Garantizamos que las carpetas existan (evita errores en limpio)
for _ruta in (RUTA_DATA_RAW, RUTA_DATA_PROCESSED, RUTA_DATA_OUTPUT,
              RUTA_LOGS, RUTA_API_CACHE):
    _ruta.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------
# Archivos de entrada / salida
# ---------------------------------------------------------------------
ARCHIVO_DATASET_MAESTRO: Path = RUTA_DATA_RAW / "dataset_donantes_argentina.xlsx"
ARCHIVO_PROYECCION_CSV: Path = RUTA_DATA_OUTPUT / "proyeccion_donantes_2030.csv"
ARCHIVO_RESUMEN_NACIONAL: Path = RUTA_DATA_OUTPUT / "resumen_nacional.csv"
ARCHIVO_METRICAS_MODELO: Path = RUTA_DATA_OUTPUT / "model_metrics.json"

# ---------------------------------------------------------------------
# Parámetros OMS / OPS
# ---------------------------------------------------------------------
OMS_OPTIMO_X1000: float = 30.0   # Donaciones por cada 1000 habitantes
TASA_ARGENTINA_BASE: float = 19.0  # OPS 2023 - punto de partida nacional

# ---------------------------------------------------------------------
# Períodos de análisis
# ---------------------------------------------------------------------
ANIO_INICIO_HISTORICO: int = 2015
ANIO_FIN_HISTORICO: int = 2024
ANIO_INICIO_PROYECCION: int = 2025
ANIO_FIN_PROYECCION: int = 2030

ANIOS_HISTORICOS = list(range(ANIO_INICIO_HISTORICO, ANIO_FIN_HISTORICO + 1))
ANIOS_PROYECCION = list(range(ANIO_INICIO_PROYECCION, ANIO_FIN_PROYECCION + 1))
TODOS_LOS_ANIOS = ANIOS_HISTORICOS + ANIOS_PROYECCION

# Años con caída por pandemia COVID
ANIOS_PANDEMIA = (2020, 2021)
IMPACTO_PANDEMIA: float = -0.15  # -15% en tasa de donación

# ---------------------------------------------------------------------
# Modelo predictivo
# ---------------------------------------------------------------------
RANDOM_STATE: int = 42
N_FOLDS_CV: int = 5
TARGET_COLUMN: str = "Tasa_Donacion_x1000"

# Hiperparámetros base (se pueden tunear con GridSearch en model.py)
PARAMS_RANDOM_FOREST = {
    "n_estimators": 200,
    "max_depth": 12,
    "min_samples_split": 4,
    "min_samples_leaf": 2,
    "random_state": RANDOM_STATE,
    "n_jobs": -1,
}

PARAMS_GRADIENT_BOOSTING = {
    "n_estimators": 300,
    "max_depth": 5,
    "learning_rate": 0.05,
    "min_samples_split": 4,
    "random_state": RANDOM_STATE,
}

# ---------------------------------------------------------------------
# Escenarios de proyección
# ---------------------------------------------------------------------
ESCENARIOS = ("pesimista", "base", "optimista")

AJUSTES_ESCENARIO = {
    "pesimista": {
        "Campañas_Donacion_Anuales": -0.15,  # -15%
        "Tasa_Desempleo": +0.20,             # +20%
        "Casos_Dengue_Anual": +0.50,         # +50%
    },
    "base": {},
    "optimista": {
        "Campañas_Donacion_Anuales": +0.50,
        "Pct_Educacion_Superior": +0.10,
        "Centros_Hemoterapia": +0.15,
    },
}

# ---------------------------------------------------------------------
# Provincias argentinas (Censo INDEC 2022)
# ---------------------------------------------------------------------
# Población total (proyección INDEC al 2024) por jurisdicción.
# Fuentes: INDEC, Censo Nacional 2022.
PROVINCIAS_ARGENTINA: dict[str, dict] = {
    "Buenos Aires":          {"poblacion_2024": 17_523_996, "region": "Centro",    "densidad": 56.9},
    "CABA":                  {"poblacion_2024":  3_120_612, "region": "Centro",    "densidad": 14_450.8},
    "Catamarca":             {"poblacion_2024":    429_557, "region": "NOA",       "densidad": 4.2},
    "Chaco":                 {"poblacion_2024":  1_142_968, "region": "NEA",       "densidad": 11.5},
    "Chubut":                {"poblacion_2024":    603_120, "region": "Patagonia", "densidad": 2.7},
    "Córdoba":               {"poblacion_2024":  3_840_905, "region": "Centro",    "densidad": 23.2},
    "Corrientes":            {"poblacion_2024":  1_212_696, "region": "NEA",       "densidad": 13.6},
    "Entre Ríos":            {"poblacion_2024":  1_426_426, "region": "Centro",    "densidad": 18.0},
    "Formosa":               {"poblacion_2024":    605_193, "region": "NEA",       "densidad": 8.4},
    "Jujuy":                 {"poblacion_2024":    811_503, "region": "NOA",       "densidad": 15.2},
    "La Pampa":              {"poblacion_2024":    366_022, "region": "Centro",    "densidad": 2.6},
    "La Rioja":              {"poblacion_2024":    393_531, "region": "NOA",       "densidad": 4.4},
    "Mendoza":               {"poblacion_2024":  2_014_533, "region": "Cuyo",      "densidad": 13.5},
    "Misiones":              {"poblacion_2024":  1_280_960, "region": "NEA",       "densidad": 43.0},
    "Neuquén":               {"poblacion_2024":    726_590, "region": "Patagonia", "densidad": 7.7},
    "Río Negro":             {"poblacion_2024":    762_067, "region": "Patagonia", "densidad": 3.7},
    "Salta":                 {"poblacion_2024":  1_424_397, "region": "NOA",       "densidad": 9.1},
    "San Juan":              {"poblacion_2024":    818_234, "region": "Cuyo",      "densidad": 9.2},
    "San Luis":              {"poblacion_2024":    540_905, "region": "Cuyo",      "densidad": 7.0},
    "Santa Cruz":            {"poblacion_2024":    337_840, "region": "Patagonia", "densidad": 1.4},
    "Santa Fe":              {"poblacion_2024":  3_556_522, "region": "Centro",    "densidad": 26.8},
    "Santiago del Estero":   {"poblacion_2024":  1_054_028, "region": "NOA",       "densidad": 7.7},
    "Tierra del Fuego":      {"poblacion_2024":    190_641, "region": "Patagonia", "densidad": 8.4},
    "Tucumán":               {"poblacion_2024":  1_703_186, "region": "NOA",       "densidad": 75.5},
}

# Códigos INDEC oficiales de jurisdicciones argentinas.
# Usados por varias fuentes oficiales (VIH, Vigilancia, etc.) en lugar de nombres.
# Referencia: INDEC - Codificación de Provincias.
CODIGO_INDEC_A_PROVINCIA: dict[int, str] = {
    2:  "CABA",
    6:  "Buenos Aires",
    10: "Catamarca",
    14: "Córdoba",
    18: "Corrientes",
    22: "Chaco",
    26: "Chubut",
    30: "Entre Ríos",
    34: "Formosa",
    38: "Jujuy",
    42: "La Pampa",
    46: "La Rioja",
    50: "Mendoza",
    54: "Misiones",
    58: "Neuquén",
    62: "Río Negro",
    66: "Salta",
    70: "San Juan",
    74: "San Luis",
    78: "Santa Cruz",
    82: "Santa Fe",
    86: "Santiago del Estero",
    90: "Tucumán",
    94: "Tierra del Fuego",
    # 200 = Total Argentina (no es jurisdicción individual)
}

# Tasa base por región (donaciones/1000) — calibrado a una media nacional ~19
TASAS_REGIONALES_BASE: dict[str, float] = {
    "Centro":    21.5,
    "Patagonia": 22.8,
    "Cuyo":      18.6,
    "NOA":       16.2,
    "NEA":       15.4,
}

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
NIVEL_LOG: str = "INFO"
FORMATO_LOG: str = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
ARCHIVO_LOG: Path = RUTA_LOGS / "pipeline.log"

# ---------------------------------------------------------------------
# APIs externas
# ---------------------------------------------------------------------
URL_DATOS_GOB: str = "https://apis.datos.gob.ar/series/api/series/"
URL_WORLD_BANK: str = "https://api.worldbank.org/v2/country/ARG/indicator/"
URL_DATOS_SALUD: str = "https://datos.salud.gob.ar"
DATASET_REFES_ID: str = (
    "listado-establecimientos-de-salud-asentados-en-el-registro-federal-refes"
)

# Capa 2 — vigilancia epidemiológica
DATASET_DENGUE_ID: str = "vigilancia-de-dengue-y-zika"
DATASET_VIH_ID: str = "notificacion-de-casos-de-vih"

# Capa 3 — recursos humanos + estadísticas vitales
DATASET_MEDICOS_ID: str = "profesionales-medicos-por-jurisdiccion"
DATASET_DEFUNCIONES_ID: str = (
    "serie-historica-de-defunciones-ocurridas-en-argentina-por-jurisdiccion"
)
DATASET_NACIMIENTOS_ID: str = (
    "serie-historica-de-nacimientos-ocurridos-en-argentina-por-jurisdiccion"
)
TIMEOUT_API: int = 30  # segundos
TIMEOUT_DESCARGA_GRANDE: int = 180  # segundos (CSVs de 5-10 MB)

# El portal datos.salud.gob.ar tiene una cadena de certificados incompleta.
# Como solo descargamos datos públicos abiertos (sin credenciales), pasamos
# verify=False con conocimiento explícito. Si en el futuro arreglan el
# certificado, podemos volver a True. Documentado en docs/metodologia.md.
VERIFICAR_SSL_DATOS_SALUD: bool = False

# ---------------------------------------------------------------------
# Catálogo de fuentes — trazabilidad por variable y KPI
# ---------------------------------------------------------------------
# Fuente única de verdad sobre el origen de cada dato que se muestra en
# la UI. Permite renderizar un ícono de fiabilidad y un popover con el
# detalle al lado de cada KPI/variable, alineado con la página
# "Cobertura Fuentes" para defensa académica.
#
# Niveles de fiabilidad:
#   "real"      🟢 — Dato observado, descargado de API oficial.
#   "calibrado" 🟡 — Sintético pero con base/tendencia oficial (INDEC, EPH, OPS).
#   "sintetico" 🔴 — 100 % sintético, sin fuente pública por jurisdicción.
#   "modelo"    🤖 — Output del modelo ML entrenado sobre los anteriores.
#   "estandar"  📏 — Constante normativa (OMS, etc.).
#   "derivado"  🧮 — Cálculo determinístico sobre otros valores del catálogo.
NIVELES_FIABILIDAD = {
    "real":      {"icono": "✅", "etiqueta": "Real (API oficial)",        "color": "#16A34A"},
    "calibrado": {"icono": "🟡", "etiqueta": "Sintético calibrado",       "color": "#F59E0B"},
    "sintetico": {"icono": "🔴", "etiqueta": "100 % sintético",           "color": "#DC2626"},
    "modelo":    {"icono": "🤖", "etiqueta": "Predicción del modelo ML",  "color": "#2563EB"},
    "estandar":  {"icono": "📏", "etiqueta": "Estándar oficial",          "color": "#7C3AED"},
    "derivado":  {"icono": "🧮", "etiqueta": "Cálculo derivado",          "color": "#0891B2"},
}

FUENTES_VARIABLES: dict[str, dict] = {
    # ---------- Variables del dataset ----------
    "Tasa_Donacion_x1000": {
        "nivel": "sintetico",
        "descripcion": "Tasa de donación de sangre por cada 1.000 habitantes (target del modelo).",
        "origen": "Calibrada a la línea base nacional ~19/1.000 (OPS 2023). "
                  "Las variaciones provinciales se generan sintéticamente porque "
                  "no hay tasas publicadas por jurisdicción.",
        "dataset": None,
        "url_dataset": None,
        "url_referencia": "https://www.paho.org/es/temas/sangre-segura",
        "anio_referencia": 2023,
        "limitacion": "Pendiente de reemplazo cuando el Plan Nacional de "
                      "Sangre publique tasas oficiales por provincia.",
    },
    "Donantes_Anuales": {
        "nivel": "sintetico",
        "descripcion": "Cantidad absoluta de donantes voluntarios por año.",
        "origen": "Derivado de Tasa_Donacion_x1000 × Población_Total / 1000.",
        "url_referencia": "https://www.paho.org/es/temas/sangre-segura",
        "limitacion": "Hereda la limitación de la tasa sintética.",
    },
    "Centros_Hemoterapia": {
        "nivel": "real",
        "descripcion": "Cantidad de centros de hemoterapia por jurisdicción.",
        "origen": "Registro Federal de Establecimientos de Salud (REFES).",
        "dataset": "listado-establecimientos-de-salud-asentados-en-el-registro-federal-refes",
        "url_dataset": "https://datos.salud.gob.ar/dataset/listado-establecimientos-de-salud-asentados-en-el-registro-federal-refes",
        "url_referencia": "https://datos.salud.gob.ar",
        "cobertura": "54,7 % (filas reales sobre total panel)",
    },
    "Casos_Dengue_Anual": {
        "nivel": "real",
        "descripcion": "Casos confirmados de dengue por año/jurisdicción.",
        "origen": "Sistema de Vigilancia Epidemiológica del Min. Salud.",
        "dataset": "vigilancia-de-dengue-y-zika",
        "url_dataset": "https://datos.salud.gob.ar/dataset/vigilancia-de-dengue-y-zika",
        "cobertura": "31,8 %",
    },
    "Casos_VIH_Anual": {
        "nivel": "real",
        "descripcion": "Casos notificados de VIH por año/jurisdicción.",
        "origen": "Plan Nacional VIH/SIDA — Min. Salud.",
        "dataset": "notificacion-de-casos-de-vih",
        "url_dataset": "https://datos.salud.gob.ar/dataset/notificacion-de-casos-de-vih",
        "cobertura": "62,5 %",
    },
    "Medicos": {
        "nivel": "real",
        "descripcion": "Cantidad de médicos por jurisdicción.",
        "origen": "MinSalud — RRHH (snapshot 2019, dataset discontinuado).",
        "dataset": "profesionales-medicos-por-jurisdiccion",
        "url_dataset": "https://datos.salud.gob.ar/dataset/profesionales-medicos-por-jurisdiccion",
        "limitacion": "El dataset oficial fue discontinuado en 2019.",
        "cobertura": "100 % (snapshot replicado año a año)",
    },
    "Defunciones_Anuales": {
        "nivel": "real",
        "descripcion": "Defunciones registradas por año/jurisdicción.",
        "origen": "Estadísticas Vitales — Min. Salud.",
        "dataset": "serie-historica-de-defunciones-ocurridas-en-argentina-por-jurisdiccion",
        "url_dataset": "https://datos.salud.gob.ar/dataset/serie-historica-de-defunciones-ocurridas-en-argentina-por-jurisdiccion",
        "cobertura": "62,5 %",
    },
    "Nacimientos_Anuales": {
        "nivel": "real",
        "descripcion": "Nacimientos registrados por año/jurisdicción.",
        "origen": "Estadísticas Vitales — Min. Salud.",
        "dataset": "serie-historica-de-nacimientos-ocurridos-en-argentina-por-jurisdiccion",
        "url_dataset": "https://datos.salud.gob.ar/dataset/serie-historica-de-nacimientos-ocurridos-en-argentina-por-jurisdiccion",
        "cobertura": "62,5 %",
    },
    "Población_Total": {
        "nivel": "calibrado",
        "descripcion": "Población total proyectada por jurisdicción y año.",
        "origen": "Censo INDEC 2022 + tasa oficial de crecimiento 0,9 % anual "
                  "(proyecciones INDEC) con variabilidad gaussiana ±0,3 %.",
        "url_referencia": "https://www.indec.gob.ar/indec/web/Nivel4-Tema-2-41-165",
        "anio_referencia": 2022,
    },
    "Población_18_65": {
        "nivel": "calibrado",
        "descripcion": "Población en edad de donar (18 a 65 años).",
        "origen": "Derivado de Población_Total × ~64 % (ratio EPH-INDEC).",
        "url_referencia": "https://www.indec.gob.ar/indec/web/Institucional-Indec-InformesTecnicos-31",
    },
    "Pct_Educacion_Superior": {
        "nivel": "calibrado",
        "descripcion": "% de población con educación superior completa.",
        "origen": "Promedios reales EPH-INDEC por región (Centro ~22 %, "
                  "NOA ~15 %, NEA ~13 %) con variabilidad ±2 %.",
        "url_referencia": "https://www.indec.gob.ar/indec/web/Institucional-Indec-InformesTecnicos-31",
    },
    "Indice_Ingreso_Promedio": {
        "nivel": "calibrado",
        "descripcion": "Índice relativo de ingreso promedio por región.",
        "origen": "Calibrado a EPH-INDEC por región, generado por código.",
        "url_referencia": "https://www.indec.gob.ar/indec/web/Institucional-Indec-InformesTecnicos-31",
    },
    "Tasa_Desempleo": {
        "nivel": "calibrado",
        "descripcion": "Tasa de desempleo (% de la PEA).",
        "origen": "Generado por región con pico real COVID 2020-21 calibrado a EPH-INDEC.",
        "url_referencia": "https://www.indec.gob.ar/indec/web/Institucional-Indec-InformesTecnicos-31",
    },
    "Pct_Cobertura_Salud": {
        "nivel": "calibrado",
        "descripcion": "% de población con cobertura de salud.",
        "origen": "Generado por región, calibrado a EPH-INDEC.",
        "url_referencia": "https://www.indec.gob.ar/indec/web/Institucional-Indec-InformesTecnicos-31",
    },
    "Campañas_Donacion_Anuales": {
        "nivel": "sintetico",
        "descripcion": "Cantidad de campañas de donación por año.",
        "origen": "Inventado proporcional a la población — no hay fuente pública.",
        "limitacion": "Pasará a 🟢 Real cuando el Plan Nacional de Sangre lo publique.",
    },

    # ---------- KPIs derivados / agregados nacionales ----------
    "Tasa_Nacional_Actual": {
        "nivel": "sintetico",
        "descripcion": "Tasa de donación nacional del último año histórico.",
        "origen": "Promedio ponderado por población de Tasa_Donacion_x1000 "
                  "del último año disponible.",
        "depende_de": ["Tasa_Donacion_x1000", "Población_Total"],
        "limitacion": "Hereda la limitación del target sintético.",
    },
    "Tasa_Nacional_Proyectada": {
        "nivel": "modelo",
        "descripcion": "Tasa de donación nacional proyectada al horizonte 2030.",
        "origen": "Predicción del modelo ML (Random Forest / Gradient Boosting "
                  "seleccionado por validación cruzada k=5) sobre features "
                  "extrapoladas de Inicio_2015 a 2030.",
        "depende_de": ["Tasa_Donacion_x1000", "Población_Total",
                        "Centros_Hemoterapia", "Pct_Educacion_Superior"],
        "limitacion": "Sujeto al MAE-CV del modelo y a la calidad del target sintético.",
    },
    "OMS_Optimo": {
        "nivel": "estandar",
        "descripcion": "Meta OMS de donaciones por 1.000 habitantes (30/1.000).",
        "origen": "Recomendación de la Organización Mundial de la Salud para "
                  "garantizar autosuficiencia en sangre segura.",
        "url_referencia": "https://www.who.int/health-topics/blood-supply",
        "valor_constante": OMS_OPTIMO_X1000,
    },
    "Brecha_OMS": {
        "nivel": "derivado",
        "descripcion": "Diferencia entre la meta OMS y la tasa proyectada.",
        "origen": "OMS_OPTIMO_X1000 (30) − Tasa_Nacional_Proyectada.",
        "depende_de": ["OMS_Optimo", "Tasa_Nacional_Proyectada"],
    },
    "Pct_Cumplimiento_OMS": {
        "nivel": "derivado",
        "descripcion": "% de cumplimiento de la meta OMS al horizonte 2030.",
        "origen": "Tasa_Nacional_Proyectada / OMS_OPTIMO_X1000 × 100.",
        "depende_de": ["OMS_Optimo", "Tasa_Nacional_Proyectada"],
    },
}
