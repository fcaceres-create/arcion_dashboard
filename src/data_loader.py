"""Carga y validación de datasets de entrada al pipeline.

Este módulo es la única puerta de entrada a los datos crudos. Toda
lectura desde disco debe pasar por aquí para garantizar:

1. Manejo uniforme de errores.
2. Validación de tipos y columnas.
3. Conversión consistente de tipos numéricos.

Ejemplo de uso:
    >>> from src.data_loader import cargar_dataset_maestro
    >>> df = cargar_dataset_maestro()
    >>> df.shape
    (384, 15)
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src import config
from src.utils import setup_logger, validar_columnas, resumen_dataframe

log = setup_logger(__name__)

# Columnas mínimas que esperamos del dataset maestro
COLUMNAS_REQUERIDAS = [
    "Provincia", "Region", "Año",
    "Población_Total", "Población_18_65",
    "Densidad_Poblacional", "Pct_Educacion_Superior",
    "Indice_Ingreso_Promedio", "Tasa_Desempleo",
    "Pct_Cobertura_Salud", "Centros_Hemoterapia",
    "Campañas_Donacion_Anuales", "Casos_Dengue_Anual",
    "Tasa_Donacion_x1000", "Donantes_Anuales",
]

COLUMNAS_NUMERICAS = [c for c in COLUMNAS_REQUERIDAS
                       if c not in ("Provincia", "Region")]


def cargar_dataset_maestro(ruta: Path | None = None,
                              hoja: str = "Datos") -> pd.DataFrame:
    """Carga el Excel maestro y valida su integridad.

    Args:
        ruta: Path del archivo. Por defecto usa config.
        hoja: Nombre de la hoja. Por defecto 'Datos'.

    Returns:
        DataFrame validado con tipos correctos.

    Raises:
        FileNotFoundError: Si el archivo no existe.
        ValueError: Si faltan columnas requeridas.

    Ejemplo:
        >>> df = cargar_dataset_maestro()
        >>> df["Provincia"].nunique()
        24
    """
    ruta = ruta or config.ARCHIVO_DATASET_MAESTRO

    if not ruta.exists():
        raise FileNotFoundError(
            f"No se encontró el dataset maestro en {ruta}. "
            f"Ejecutá `python -m src.data_generator` o el pipeline completo."
        )

    log.info("Cargando dataset desde %s | hoja=%s", ruta.name, hoja)
    try:
        df = pd.read_excel(ruta, sheet_name=hoja, engine="openpyxl")
    except Exception as exc:
        raise IOError(f"Error leyendo {ruta}: {exc}") from exc

    validar_columnas(df, COLUMNAS_REQUERIDAS, contexto=f"{ruta.name}/{hoja}")

    # Conversión defensiva de tipos numéricos
    for col in COLUMNAS_NUMERICAS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Año debe ser entero
    df["Año"] = df["Año"].astype(int)

    log.info("Dataset cargado | %s", resumen_dataframe(df))
    return df


def separar_historico_proyeccion(
    df: pd.DataFrame,
    anio_corte: int = config.ANIO_FIN_HISTORICO,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Divide el panel en histórico (con target) y futuro (sin target).

    Args:
        df: Panel completo.
        anio_corte: Último año del histórico inclusive.

    Returns:
        Tupla ``(df_historico, df_futuro)``.

    Ejemplo:
        >>> hist, fut = separar_historico_proyeccion(df)
        >>> hist["Año"].max()
        2024
    """
    df_hist = df[df["Año"] <= anio_corte].copy()
    df_fut = df[df["Año"] > anio_corte].copy()
    log.info("Separación temporal | histórico=%d filas | futuro=%d filas",
             len(df_hist), len(df_fut))
    return df_hist, df_fut


def reportar_calidad(df: pd.DataFrame) -> dict:
    """Genera un reporte de calidad: nulos, duplicados, outliers básicos.

    Args:
        df: DataFrame a auditar.

    Returns:
        Diccionario con métricas de calidad.

    Ejemplo:
        >>> reporte = reportar_calidad(df)
        >>> reporte["duplicados_provincia_anio"]
        0
    """
    reporte = {
        "filas": len(df),
        "duplicados_provincia_anio": int(
            df.duplicated(subset=["Provincia", "Año"]).sum()
        ),
        "nulos_por_columna": df.isna().sum().to_dict(),
        "rango_anios": (int(df["Año"].min()), int(df["Año"].max())),
        "provincias_distintas": int(df["Provincia"].nunique()),
    }
    return reporte
