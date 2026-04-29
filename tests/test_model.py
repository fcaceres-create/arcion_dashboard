"""Tests para src.model."""
from __future__ import annotations

import pytest

from src.model import (
    MetricasModelo, ResultadoModelo, entrenar_y_seleccionar,
)


@pytest.fixture(scope="module")
def resultado(df_features):
    """Entrena el modelo una sola vez por módulo (es caro)."""
    return entrenar_y_seleccionar(df_features, guardar_metricas=False)


def test_devuelve_resultado_modelo(resultado):
    """El entrenamiento debe devolver un ResultadoModelo completo."""
    assert isinstance(resultado, ResultadoModelo)
    assert resultado.nombre_mejor in ("RandomForest", "GradientBoosting")


def test_ambos_modelos_evaluados(resultado):
    """Las métricas deben incluir ambos candidatos."""
    assert "RandomForest" in resultado.metricas
    assert "GradientBoosting" in resultado.metricas


def test_metricas_son_razonables(resultado):
    """MAE-CV debe estar en rango sensato; R² debe ser positivo."""
    for nombre, m in resultado.metricas.items():
        assert isinstance(m, MetricasModelo)
        # MAE-CV no debería superar 5 unidades de tasa para un dataset sintético
        assert 0 < m.mae_cv < 5, f"{nombre} MAE-CV fuera de rango: {m.mae_cv}"
        # R² entrenamiento positivo (mejor que la media)
        assert m.r2_train > 0, f"{nombre} R² no positivo"


def test_seleccion_es_la_de_menor_mae(resultado):
    """El nombre_mejor debe ser efectivamente el de MAE-CV más bajo."""
    mae_por_modelo = {n: m.mae_cv for n, m in resultado.metricas.items()}
    esperado = min(mae_por_modelo, key=mae_por_modelo.get)
    assert resultado.nombre_mejor == esperado


def test_feature_importance_no_vacia(resultado):
    """El modelo elegido debe reportar al menos una feature importante."""
    importancias = resultado.metricas[resultado.nombre_mejor].feature_importance
    assert len(importancias) > 0
    # La suma de importancias en árboles debe rondar 1.0
    suma = sum(importancias.values())
    assert 0.9 <= suma <= 1.1


def test_columnas_features_estan_en_dataframe(resultado, df_features):
    """Todas las columnas que usa el modelo deben existir en el DataFrame."""
    cols_faltantes = set(resultado.columnas_features) - set(df_features.columns)
    assert not cols_faltantes
