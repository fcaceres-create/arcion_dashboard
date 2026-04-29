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
