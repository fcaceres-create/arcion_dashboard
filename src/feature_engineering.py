"""Ingeniería de features para el modelo predictivo.

Aplica transformaciones que NO existen en el dataset crudo pero que
mejoran la capacidad explicativa del modelo:

- Encoding one-hot de la región (categórica).
- Features derivadas: ratio centros/población, campañas per cápita, etc.
- Lag-1 de la tasa (memoria del año anterior) — útil porque el target
  tiene fuerte autocorrelación temporal.
- Indicador binario de pandemia.

Ejemplo de uso:
    >>> from src.feature_engineering import construir_features
    >>> df_features = construir_features(df_panel)
    >>> df_features.shape
    (384, 22)
"""
from __future__ import annotations

import pandas as pd

from src import config
from src.utils import setup_logger

log = setup_logger(__name__)

# Variables predictoras finales que entran al modelo
FEATURES_NUMERICAS = [
    "Población_Total",
    "Población_18_65",
    "Densidad_Poblacional",
    "Pct_Educacion_Superior",
    "Indice_Ingreso_Promedio",
    "Tasa_Desempleo",
    "Pct_Cobertura_Salud",
    "Centros_Hemoterapia",
    "Campañas_Donacion_Anuales",
    "Casos_Dengue_Anual",
    "Casos_VIH_Anual",
    "Medicos",
    "Defunciones_Anuales",
    "Nacimientos_Anuales",
    "Año",
    # Derivadas
    "Centros_x_100k_hab",
    "Campañas_per_capita",
    "Casos_Dengue_x_1000_hab",
    "Casos_VIH_x_1000_hab",
    "Medicos_x_1000_hab",
    "Tasa_Mortalidad_Bruta",
    "Tasa_Natalidad_Bruta",
    "Pct_Pob_18_65",
    "Es_Pandemia",
    "Tasa_Donacion_Lag1",
]


def _agregar_features_derivadas(df: pd.DataFrame) -> pd.DataFrame:
    """Calcula ratios y proporciones a partir de las variables base.

    Args:
        df: DataFrame con las columnas crudas del dataset maestro.

    Returns:
        DataFrame con columnas adicionales (in-place no, retorna copia).
    """
    df = df.copy()

    # Centros de hemoterapia por cada 100.000 habitantes
    df["Centros_x_100k_hab"] = (
        df["Centros_Hemoterapia"] / df["Población_Total"] * 100_000
    ).round(3)

    # Campañas per cápita (×100k)
    df["Campañas_per_capita"] = (
        df["Campañas_Donacion_Anuales"] / df["Población_Total"] * 100_000
    ).round(3)

    # Casos de dengue cada 1000 hab (presión epidemiológica)
    df["Casos_Dengue_x_1000_hab"] = (
        df["Casos_Dengue_Anual"] / df["Población_Total"] * 1000
    ).round(3)

    # Casos VIH cada 1000 hab
    df["Casos_VIH_x_1000_hab"] = (
        df["Casos_VIH_Anual"] / df["Población_Total"] * 1000
    ).round(3)

    # Médicos cada 1000 hab (densidad sanitaria)
    df["Medicos_x_1000_hab"] = (
        df["Medicos"] / df["Población_Total"] * 1000
    ).round(3)

    # Tasas demográficas brutas
    df["Tasa_Mortalidad_Bruta"] = (
        df["Defunciones_Anuales"] / df["Población_Total"] * 1000
    ).round(3)
    df["Tasa_Natalidad_Bruta"] = (
        df["Nacimientos_Anuales"] / df["Población_Total"] * 1000
    ).round(3)

    # Proporción de población elegible para donar
    df["Pct_Pob_18_65"] = (
        df["Población_18_65"] / df["Población_Total"] * 100
    ).round(2)

    # Indicador binario de año pandémico
    df["Es_Pandemia"] = df["Año"].isin(config.ANIOS_PANDEMIA).astype(int)

    return df


def _agregar_lag_target(df: pd.DataFrame) -> pd.DataFrame:
    """Agrega la tasa del año anterior como predictor.

    Es la variable más informativa cuando existe (autocorrelación alta),
    pero requiere imputación cuidadosa para los años de proyección.

    Args:
        df: DataFrame ordenado por Provincia, Año.

    Returns:
        DataFrame con columna ``Tasa_Donacion_Lag1``.
    """
    df = df.sort_values(["Provincia", "Año"]).copy()
    df["Tasa_Donacion_Lag1"] = df.groupby("Provincia")["Tasa_Donacion_x1000"].shift(1)

    # Imputación del primer año por provincia con la mediana provincial histórica
    medianas_prov = df.groupby("Provincia")["Tasa_Donacion_x1000"].transform("median")
    df["Tasa_Donacion_Lag1"] = df["Tasa_Donacion_Lag1"].fillna(medianas_prov)
    # Si todavía hay nulos (provincia sin histórico), uso media nacional
    df["Tasa_Donacion_Lag1"] = df["Tasa_Donacion_Lag1"].fillna(
        config.TASA_ARGENTINA_BASE
    )
    return df


def _encoding_region(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica one-hot encoding sobre la columna 'Region'.

    Conserva la columna original para uso en el dashboard,
    y agrega columnas dummies para el modelo.
    """
    dummies = pd.get_dummies(df["Region"], prefix="Region", dtype=int)
    return pd.concat([df, dummies], axis=1)


def construir_features(df: pd.DataFrame,
                          incluir_lag: bool = True) -> pd.DataFrame:
    """Pipeline completo de feature engineering.

    Args:
        df: Panel crudo (output de ``cargar_dataset_maestro``).
        incluir_lag: Si False, omite la lag-1 (útil cuando el target no
            está disponible y se hace predicción rolling).

    Returns:
        DataFrame enriquecido, listo para ``model.entrenar``.

    Ejemplo:
        >>> df_feat = construir_features(df_panel)
        >>> "Centros_x_100k_hab" in df_feat.columns
        True
    """
    log.info("Construyendo features | filas=%d", len(df))
    df = _agregar_features_derivadas(df)

    if incluir_lag:
        df = _agregar_lag_target(df)
    else:
        df["Tasa_Donacion_Lag1"] = config.TASA_ARGENTINA_BASE

    df = _encoding_region(df)
    log.info("Features finales: %d columnas", len(df.columns))
    return df


def obtener_columnas_modelo(df: pd.DataFrame) -> list[str]:
    """Devuelve el listado de columnas que efectivamente entran al modelo.

    Combina las features numéricas declaradas con las dummies de región
    presentes en el DataFrame.

    Ejemplo:
        >>> cols = obtener_columnas_modelo(df_features)
        >>> len(cols) >= 17
        True
    """
    cols_region = [c for c in df.columns if c.startswith("Region_")]
    return FEATURES_NUMERICAS + cols_region
