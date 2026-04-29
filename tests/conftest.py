"""Configuración de pytest: fixtures compartidos entre tests."""
from __future__ import annotations

import sys
from pathlib import Path

# Agrega la raíz del proyecto al path para imports limpios desde los tests
RUTA_RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RUTA_RAIZ))

import pytest  # noqa: E402

from src import config  # noqa: E402
from src.data_generator import generar_dataset_maestro  # noqa: E402
from src.data_loader import cargar_dataset_maestro  # noqa: E402
from src.feature_engineering import construir_features  # noqa: E402


@pytest.fixture(scope="session")
def dataset_maestro(tmp_path_factory):
    """Genera el dataset sintético una sola vez por sesión.

    Usa un directorio temporal aislado para no contaminar data/raw.
    """
    tmp_dir = tmp_path_factory.mktemp("data_test")
    ruta = tmp_dir / "dataset_test.xlsx"
    generar_dataset_maestro(ruta_destino=ruta, semilla=42)
    return ruta


@pytest.fixture(scope="session")
def df_panel(dataset_maestro):
    """Carga el panel completo desde el dataset de test."""
    return cargar_dataset_maestro(ruta=dataset_maestro)


@pytest.fixture(scope="session")
def df_features(df_panel):
    """Panel histórico con feature engineering aplicado."""
    df_hist = df_panel[df_panel["Año"] <= config.ANIO_FIN_HISTORICO].copy()
    return construir_features(df_hist)
