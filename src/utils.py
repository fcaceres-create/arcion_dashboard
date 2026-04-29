"""Utilidades transversales: logging configurado, formateo y validaciones.

Ejemplo de uso:
    >>> from src.utils import setup_logger, formato_numero_argentino
    >>> log = setup_logger(__name__)
    >>> log.info("Pipeline iniciado")
    >>> formato_numero_argentino(1234567.89)
    '1.234.567,89'
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from src import config

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------
_LOGGERS_CONFIGURADOS: set[str] = set()


def setup_logger(nombre: str = "donantes_arg",
                 archivo: Path | None = None,
                 nivel: str | None = None) -> logging.Logger:
    """Configura un logger con handlers de consola y archivo.

    Args:
        nombre: Identificador del logger (típicamente ``__name__``).
        archivo: Ruta del archivo de log. Si es ``None`` usa el de config.
        nivel: Nivel ('DEBUG', 'INFO', 'WARNING', 'ERROR'). Por defecto INFO.

    Returns:
        Logger ya configurado y listo para usar.

    Ejemplo:
        >>> log = setup_logger("mi_modulo")
        >>> log.info("Mensaje de prueba")
    """
    if nombre in _LOGGERS_CONFIGURADOS:
        return logging.getLogger(nombre)

    archivo = archivo or config.ARCHIVO_LOG
    nivel = (nivel or config.NIVEL_LOG).upper()

    logger = logging.getLogger(nombre)
    logger.setLevel(getattr(logging, nivel, logging.INFO))
    logger.propagate = False

    formato = logging.Formatter(config.FORMATO_LOG)

    # Handler de consola (forzamos UTF-8 en stdout en Windows para evitar
    # UnicodeEncodeError con caracteres como flechas o tildes que vienen
    # de fuentes externas como REFES).
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except (AttributeError, ValueError):
        pass
    handler_consola = logging.StreamHandler(sys.stdout)
    handler_consola.setFormatter(formato)
    logger.addHandler(handler_consola)

    # Handler de archivo
    archivo.parent.mkdir(parents=True, exist_ok=True)
    handler_archivo = logging.FileHandler(archivo, encoding="utf-8")
    handler_archivo.setFormatter(formato)
    logger.addHandler(handler_archivo)

    _LOGGERS_CONFIGURADOS.add(nombre)
    return logger


# ---------------------------------------------------------------------
# Formateo argentino
# ---------------------------------------------------------------------
def formato_numero_argentino(valor: float, decimales: int = 2) -> str:
    """Formatea un número con punto como separador de miles y coma decimal.

    Args:
        valor: Número a formatear.
        decimales: Cantidad de decimales a mostrar.

    Returns:
        String con formato argentino (ej. ``'1.234.567,89'``).

    Ejemplo:
        >>> formato_numero_argentino(1234567.89)
        '1.234.567,89'
        >>> formato_numero_argentino(19.5, decimales=1)
        '19,5'
    """
    if pd.isna(valor):
        return "—"
    formato_us = f"{valor:,.{decimales}f}"
    # Intercambio: , -> X (placeholder), . -> , , X -> .
    return formato_us.replace(",", "X").replace(".", ",").replace("X", ".")


def formato_porcentaje(valor: float, decimales: int = 1) -> str:
    """Formatea un valor como porcentaje en español.

    Ejemplo:
        >>> formato_porcentaje(0.6533)
        '65,3%'
    """
    if pd.isna(valor):
        return "—"
    return f"{formato_numero_argentino(valor * 100, decimales)}%"


# ---------------------------------------------------------------------
# Validaciones de DataFrames
# ---------------------------------------------------------------------
def validar_columnas(df: pd.DataFrame,
                     columnas_requeridas: list[str],
                     contexto: str = "DataFrame") -> None:
    """Valida que un DataFrame contenga las columnas necesarias.

    Args:
        df: DataFrame a validar.
        columnas_requeridas: Lista de nombres de columnas obligatorios.
        contexto: Texto descriptivo para el mensaje de error.

    Raises:
        ValueError: Si faltan columnas.

    Ejemplo:
        >>> validar_columnas(df, ['Provincia', 'Año'], 'dataset principal')
    """
    faltantes = set(columnas_requeridas) - set(df.columns)
    if faltantes:
        raise ValueError(
            f"[{contexto}] Faltan columnas requeridas: {sorted(faltantes)}. "
            f"Columnas presentes: {sorted(df.columns.tolist())}"
        )


def normalizar_provincia(nombre: str) -> str:
    """Convierte un nombre de provincia a forma canónica para joins.

    Útil para cruzar fuentes que usan grafías distintas (mayúsculas,
    acentos opcionales, "CABA" vs "Ciudad Autónoma de Buenos Aires").

    Args:
        nombre: Nombre tal como viene de la fuente externa.

    Returns:
        Cadena lowercase, sin acentos, sin espacios extra.

    Ejemplo:
        >>> normalizar_provincia("CÓRDOBA")
        'cordoba'
        >>> normalizar_provincia("Tierra del Fuego")
        'tierra del fuego'
        >>> normalizar_provincia("CIUDAD AUTONOMA DE BUENOS AIRES")
        'caba'
    """
    import unicodedata
    if not isinstance(nombre, str):
        return ""
    s = nombre.strip().lower()
    # Remueve acentos
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    # Aliases conocidos
    aliases = {
        "ciudad autonoma de buenos aires": "caba",
        "ciudad de buenos aires": "caba",
        "capital federal": "caba",
        "tierra del fuego, antartida e islas del atlantico sur": "tierra del fuego",
    }
    return aliases.get(s, s)


def resumen_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """Devuelve un diccionario resumen del DataFrame para logging.

    Ejemplo:
        >>> info = resumen_dataframe(df)
        >>> log.info(f"Cargado: {info}")
    """
    return {
        "filas": len(df),
        "columnas": len(df.columns),
        "memoria_kb": round(df.memory_usage(deep=True).sum() / 1024, 1),
        "nulos_totales": int(df.isna().sum().sum()),
    }
