"""Tests para src.data_loader."""
from __future__ import annotations

import pandas as pd
import pytest

from src import config
from src.data_loader import (
    cargar_dataset_maestro, reportar_calidad,
    separar_historico_proyeccion, COLUMNAS_REQUERIDAS,
)


def test_dataset_se_carga_sin_errores(df_panel):
    """El dataset sintético debe leerse y validarse sin lanzar excepciones."""
    assert isinstance(df_panel, pd.DataFrame)
    assert not df_panel.empty


def test_dataset_tiene_24_provincias(df_panel):
    """Argentina = 23 provincias + CABA = 24 jurisdicciones."""
    assert df_panel["Provincia"].nunique() == 24


def test_dataset_cubre_periodo_completo(df_panel):
    """Debe haber filas para todos los años 2015-2030."""
    anios = set(df_panel["Año"].unique().tolist())
    assert anios == set(config.TODOS_LOS_ANIOS)


def test_dataset_tiene_todas_las_columnas(df_panel):
    """Validar que las columnas requeridas estén presentes."""
    faltantes = set(COLUMNAS_REQUERIDAS) - set(df_panel.columns)
    assert not faltantes, f"Faltan columnas: {faltantes}"


def test_target_solo_en_historico(df_panel):
    """El target debe estar nulo en años de proyección y poblado en histórico."""
    df_hist = df_panel[df_panel["Año"] <= config.ANIO_FIN_HISTORICO]
    df_fut = df_panel[df_panel["Año"] > config.ANIO_FIN_HISTORICO]

    assert df_hist["Tasa_Donacion_x1000"].notna().all()
    assert df_fut["Tasa_Donacion_x1000"].isna().all()


def test_tasas_realistas(df_panel):
    """Las tasas deben estar en rangos sensatos: nada por debajo de 8 ni encima de 35."""
    tasas = df_panel["Tasa_Donacion_x1000"].dropna()
    assert tasas.min() >= 8.0
    assert tasas.max() <= 35.0
    # La media nacional debería rondar la línea base OPS (~19)
    assert 16.0 <= tasas.mean() <= 23.0


def test_separar_historico_proyeccion(df_panel):
    """La separación temporal debe respetar el año de corte."""
    hist, fut = separar_historico_proyeccion(df_panel)
    assert hist["Año"].max() == config.ANIO_FIN_HISTORICO
    assert fut["Año"].min() == config.ANIO_INICIO_PROYECCION


def test_no_hay_duplicados_provincia_anio(df_panel):
    """No deben existir duplicados (Provincia, Año)."""
    reporte = reportar_calidad(df_panel)
    assert reporte["duplicados_provincia_anio"] == 0


def test_archivo_inexistente_lanza_error():
    """Cargar un archivo inexistente debe lanzar FileNotFoundError."""
    from pathlib import Path
    with pytest.raises(FileNotFoundError):
        cargar_dataset_maestro(ruta=Path("/ruta/que/no/existe.xlsx"))
