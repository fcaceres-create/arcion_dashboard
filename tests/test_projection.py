"""Tests para src.projection."""
from __future__ import annotations

import pytest

from src import config
from src.model import entrenar_y_seleccionar
from src.projection import (
    construir_resumen_nacional, generar_proyecciones,
    proyectar_features_completo,
)


@pytest.fixture(scope="module")
def proyeccion(df_panel, df_features):
    """Genera proyecciones una sola vez por módulo."""
    df_hist = df_panel[df_panel["Año"] <= config.ANIO_FIN_HISTORICO].copy()
    resultado = entrenar_y_seleccionar(df_features, guardar_metricas=False)
    df_completo = proyectar_features_completo(df_hist)
    return generar_proyecciones(resultado, df_completo)


def test_proyeccion_tiene_3_escenarios(proyeccion):
    """El output debe contener histórico + 3 escenarios."""
    escenarios = set(proyeccion["Escenario"].unique())
    assert {"historico", "pesimista", "base", "optimista"} == escenarios


def test_proyeccion_cubre_2025_2030(proyeccion):
    """Cada escenario debe tener proyección para 2025-2030."""
    for esc in config.ESCENARIOS:
        sub = proyeccion[proyeccion["Escenario"] == esc]
        anios = set(sub["Año"].unique())
        assert anios == set(config.ANIOS_PROYECCION), \
            f"Escenario {esc} no cubre todos los años"


def test_proyeccion_tasas_no_negativas(proyeccion):
    """No deben aparecer tasas negativas o absurdamente altas."""
    tasas = proyeccion["Tasa_Donacion_x1000"].dropna()
    assert tasas.min() >= 0
    assert tasas.max() <= 50


def test_donantes_calculados_correctamente(proyeccion):
    """Donantes_Anuales = Tasa × Población / 1000 (tolerancia ±2 por redondeo)."""
    df = proyeccion.dropna(subset=["Tasa_Donacion_x1000", "Donantes_Anuales"]).copy()
    df["esperado"] = (df["Tasa_Donacion_x1000"] * df["Población_Total"] / 1000).round()
    df["diff"] = (df["esperado"] - df["Donantes_Anuales"]).abs()
    assert (df["diff"] <= 2).all()


def test_brecha_oms_consistente(proyeccion):
    """Brecha = Necesarios - Reales."""
    df = proyeccion.dropna(subset=["Donantes_Anuales", "Donantes_OMS_Necesarios"])
    diferencia = (df["Donantes_OMS_Necesarios"] - df["Donantes_Anuales"]) - df["Brecha_Donantes"]
    assert (diferencia.abs() < 1).all()


def test_optimista_mejor_que_pesimista(proyeccion):
    """En 2030, escenario optimista debe tener tasa nacional ≥ pesimista."""
    df_2030 = proyeccion[proyeccion["Año"] == config.ANIO_FIN_PROYECCION]
    tasa_pes = df_2030[df_2030["Escenario"] == "pesimista"]["Tasa_Donacion_x1000"].mean()
    tasa_opt = df_2030[df_2030["Escenario"] == "optimista"]["Tasa_Donacion_x1000"].mean()
    assert tasa_opt >= tasa_pes, \
        f"Optimista ({tasa_opt:.2f}) debería ser >= pesimista ({tasa_pes:.2f})"


def test_resumen_nacional_consistente(proyeccion):
    """El resumen nacional debe agregarse correctamente."""
    resumen = construir_resumen_nacional(proyeccion)
    assert not resumen.empty
    assert "Tasa_Nacional_x1000" in resumen.columns
    # La tasa nacional debe estar en rango razonable
    tasas = resumen["Tasa_Nacional_x1000"].dropna()
    assert tasas.min() >= 8
    assert tasas.max() <= 35
