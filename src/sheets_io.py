"""Lectura/escritura de Google Sheets como backend persistente.

Este módulo encapsula toda la integración con Google Sheets para que el
resto de la app trabaje con DataFrames sin preocuparse del transporte.

Configuración requerida en ``.streamlit/secrets.toml`` (o en Streamlit
Cloud Secrets):

.. code-block:: toml

    [google_sheets]
    sheet_id = "<<ID DEL SPREADSHEET>>"
    credentials_json = '''
    { ... JSON del service account de Google Cloud ... }
    '''

    [admin]
    password = "<<password del editor>>"

Ejemplo de uso:
    >>> from src.sheets_io import leer_hoja, escribir_hoja
    >>> df = leer_hoja("Datos")
    >>> df.shape
    (384, 17)
"""
from __future__ import annotations

import json
from typing import Any

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials

from src.utils import setup_logger

log = setup_logger(__name__)

# Scopes mínimos necesarios. Drive permite abrir el Sheet por ID; Sheets
# permite leer/escribir celdas.
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.file",
]


# ---------------------------------------------------------------------
# Configuración / cliente
# ---------------------------------------------------------------------
def _obtener_secrets() -> dict[str, Any]:
    """Carga los secrets de Streamlit. Falla con mensaje claro si faltan."""
    try:
        import streamlit as st
    except ImportError as exc:
        raise RuntimeError(
            "El módulo sheets_io requiere ejecutarse dentro de una sesión "
            "de Streamlit (para acceder a st.secrets)."
        ) from exc

    if "google_sheets" not in st.secrets:
        raise RuntimeError(
            "Faltan secrets [google_sheets]. Configurá sheet_id y "
            "credentials_json en Streamlit Cloud → Settings → Secrets."
        )
    return st.secrets


def _construir_cliente() -> gspread.Client:
    """Autentica con Service Account y devuelve un cliente gspread."""
    secrets = _obtener_secrets()
    creds_str = secrets["google_sheets"]["credentials_json"]
    try:
        creds_dict = json.loads(creds_str)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            "credentials_json no es un JSON válido. Revisá que copiaste "
            "el contenido completo del archivo del service account."
        ) from exc

    credentials = Credentials.from_service_account_info(
        creds_dict, scopes=SCOPES
    )
    return gspread.authorize(credentials)


def _abrir_spreadsheet():
    """Abre el spreadsheet configurado en secrets."""
    secrets = _obtener_secrets()
    sheet_id = secrets["google_sheets"]["sheet_id"]
    cliente = _construir_cliente()
    return cliente.open_by_key(sheet_id)


# ---------------------------------------------------------------------
# API pública
# ---------------------------------------------------------------------
def listar_hojas() -> list[str]:
    """Devuelve los nombres de todas las pestañas del Sheet.

    Ejemplo:
        >>> listar_hojas()
        ['Datos', 'Diccionario', 'Resumen_Nacional', 'Notas']
    """
    spreadsheet = _abrir_spreadsheet()
    return [ws.title for ws in spreadsheet.worksheets()]


def leer_hoja(nombre_hoja: str) -> pd.DataFrame:
    """Lee una pestaña completa y la devuelve como DataFrame.

    Args:
        nombre_hoja: Nombre exacto de la pestaña (case-sensitive).

    Returns:
        DataFrame con los datos. Hoja vacía → DataFrame vacío sin columnas.

    Raises:
        gspread.WorksheetNotFound: Si la pestaña no existe.

    Ejemplo:
        >>> df = leer_hoja("Datos")
        >>> df.head()
    """
    log.info("Leyendo hoja '%s' de Google Sheets...", nombre_hoja)
    spreadsheet = _abrir_spreadsheet()
    worksheet = spreadsheet.worksheet(nombre_hoja)
    valores = worksheet.get_all_values()
    if not valores:
        return pd.DataFrame()
    encabezados, *filas = valores
    df = pd.DataFrame(filas, columns=encabezados)
    return _convertir_tipos(df)


def escribir_hoja(nombre_hoja: str, df: pd.DataFrame,
                    crear_si_no_existe: bool = True) -> None:
    """Sobrescribe completamente una pestaña con el contenido del DataFrame.

    Args:
        nombre_hoja: Pestaña destino.
        df: DataFrame a escribir (incluye encabezados de columna).
        crear_si_no_existe: Si True, crea la pestaña si no existe.

    Ejemplo:
        >>> escribir_hoja("Datos", df_actualizado)
    """
    log.info("Escribiendo hoja '%s' (%d filas) a Google Sheets...",
             nombre_hoja, len(df))
    spreadsheet = _abrir_spreadsheet()
    try:
        worksheet = spreadsheet.worksheet(nombre_hoja)
    except gspread.WorksheetNotFound:
        if not crear_si_no_existe:
            raise
        worksheet = spreadsheet.add_worksheet(
            title=nombre_hoja,
            rows=max(len(df) + 5, 100),
            cols=max(len(df.columns) + 2, 10),
        )

    worksheet.clear()
    if df.empty:
        return

    # gspread espera lista de listas con strings/números
    df_str = df.copy()
    # Convertimos NaN a vacío y todo a tipo serializable
    df_str = df_str.fillna("").astype(str)
    valores = [df_str.columns.tolist()] + df_str.values.tolist()
    worksheet.update(values=valores, range_name="A1")


def _convertir_tipos(df: pd.DataFrame) -> pd.DataFrame:
    """Intenta convertir columnas numéricas que vienen como string.

    Sheets devuelve todo como string. Las columnas que parecen números
    se convierten para que el resto de la app las trate como tales.
    """
    for col in df.columns:
        # Saltamos columnas claramente textuales
        if col.lower() in ("provincia", "region", "escenario", "tipo_año",
                            "fuente", "variable"):
            continue
        try:
            convertida = pd.to_numeric(df[col], errors="coerce")
            # Solo reemplazo si más del 80% de los valores se convirtieron
            tasa_exito = convertida.notna().sum() / max(len(df), 1)
            if tasa_exito > 0.8:
                df[col] = convertida
        except Exception:  # noqa: BLE001
            continue
    return df


# ---------------------------------------------------------------------
# Helper de inicialización (carga inicial desde data_generator)
# ---------------------------------------------------------------------
def inicializar_sheet_con_sinteticos() -> dict[str, int]:
    """Genera datos sintéticos y los sube al Sheet (carga inicial).

    Útil cuando se acaba de configurar el Sheet y está vacío. Genera el
    panel sintético en memoria (sin tocar disco) y escribe las 4 hojas.

    Returns:
        Dict con la cantidad de filas escritas por hoja.

    Ejemplo:
        >>> resumen = inicializar_sheet_con_sinteticos()
        >>> resumen
        {'Datos': 384, 'Diccionario': 19, 'Resumen_Nacional': 10, 'Notas': 25}
    """
    from src.data_generator import (
        _generar_features_provincia, _hoja_diccionario, _hoja_notas,
        _hoja_resumen_nacional,
    )
    from src import config
    import numpy as np

    log.info("Inicializando Sheet con datos sintéticos...")
    rng = np.random.default_rng(config.RANDOM_STATE)
    paneles = [
        _generar_features_provincia(prov, datos, rng)
        for prov, datos in config.PROVINCIAS_ARGENTINA.items()
    ]
    df_datos = pd.concat(paneles, ignore_index=True)

    hojas = {
        "Datos": df_datos,
        "Diccionario": _hoja_diccionario(),
        "Resumen_Nacional": _hoja_resumen_nacional(df_datos),
        "Notas": _hoja_notas(),
    }
    resumen = {}
    for nombre, df in hojas.items():
        escribir_hoja(nombre, df)
        resumen[nombre] = len(df)
    log.info("Sheet inicializado: %s", resumen)
    return resumen
