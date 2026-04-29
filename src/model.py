"""Entrenamiento, validación y selección de modelo.

Compara Random Forest vs Gradient Boosting mediante K-Fold CV (k=5)
usando MAE como métrica primaria, y reporta también R² y RMSE en
entrenamiento. Selecciona automáticamente el mejor modelo y devuelve
un objeto ``ResultadoModelo`` con todo lo necesario para proyectar.

Ejemplo de uso:
    >>> from src.model import entrenar_y_seleccionar
    >>> resultado = entrenar_y_seleccionar(df_features)
    >>> resultado.nombre_mejor
    'GradientBoosting'
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, cross_val_score

from src import config
from src.feature_engineering import obtener_columnas_modelo
from src.utils import setup_logger

log = setup_logger(__name__)


# ---------------------------------------------------------------------
# Estructura de resultado
# ---------------------------------------------------------------------
@dataclass
class MetricasModelo:
    """Métricas de un modelo individual."""
    nombre: str
    mae_cv: float
    mae_cv_std: float
    r2_train: float
    rmse_train: float
    feature_importance: dict[str, float] = field(default_factory=dict)


@dataclass
class ResultadoModelo:
    """Resultado completo del entrenamiento y selección."""
    nombre_mejor: str
    modelo_mejor: Any
    columnas_features: list[str]
    metricas: dict[str, MetricasModelo]

    def to_dict(self) -> dict:
        """Convierte a dict serializable a JSON."""
        return {
            "nombre_mejor": self.nombre_mejor,
            "columnas_features": self.columnas_features,
            "metricas": {k: asdict(v) for k, v in self.metricas.items()},
        }


# ---------------------------------------------------------------------
# Pipeline de entrenamiento
# ---------------------------------------------------------------------
def _construir_modelos() -> dict[str, Any]:
    """Devuelve los modelos candidatos con sus hiperparámetros base."""
    return {
        "RandomForest": RandomForestRegressor(**config.PARAMS_RANDOM_FOREST),
        "GradientBoosting": GradientBoostingRegressor(**config.PARAMS_GRADIENT_BOOSTING),
    }


def _evaluar_cv(modelo, X: pd.DataFrame, y: pd.Series) -> tuple[float, float]:
    """Evalúa un modelo con K-Fold CV y devuelve (MAE_medio, std).

    Args:
        modelo: Estimador scikit-learn.
        X: Features.
        y: Target.

    Returns:
        Tupla (MAE medio, desvío estándar del MAE).
    """
    kf = KFold(
        n_splits=config.N_FOLDS_CV,
        shuffle=True,
        random_state=config.RANDOM_STATE,
    )
    scores = cross_val_score(
        modelo, X, y,
        cv=kf,
        scoring="neg_mean_absolute_error",
        n_jobs=-1,
    )
    return float(-scores.mean()), float(scores.std())


def _calcular_metricas_train(modelo, X: pd.DataFrame, y: pd.Series) -> dict:
    """Calcula R² y RMSE sobre los datos de entrenamiento."""
    pred = modelo.predict(X)
    return {
        "r2_train": float(r2_score(y, pred)),
        "rmse_train": float(np.sqrt(mean_squared_error(y, pred))),
    }


def _extraer_feature_importance(modelo, columnas: list[str]) -> dict[str, float]:
    """Devuelve la importancia de variables ordenada de mayor a menor."""
    if not hasattr(modelo, "feature_importances_"):
        return {}
    importancias = sorted(
        zip(columnas, modelo.feature_importances_),
        key=lambda x: x[1], reverse=True,
    )
    return {col: float(round(imp, 4)) for col, imp in importancias}


def entrenar_y_seleccionar(df_features: pd.DataFrame,
                              guardar_metricas: bool = True) -> ResultadoModelo:
    """Entrena los modelos candidatos y selecciona el mejor por MAE-CV.

    Args:
        df_features: DataFrame con features y target (solo histórico).
        guardar_metricas: Si True, escribe las métricas a JSON en disk.

    Returns:
        ``ResultadoModelo`` con el modelo ganador y todas las métricas.

    Raises:
        ValueError: Si no hay filas con target válido.

    Ejemplo:
        >>> resultado = entrenar_y_seleccionar(df_features)
        >>> print(resultado.metricas[resultado.nombre_mejor].mae_cv)
    """
    # Filtrar solo filas con target conocido
    df_train = df_features.dropna(subset=[config.TARGET_COLUMN]).copy()
    if df_train.empty:
        raise ValueError("No hay filas con target para entrenar.")

    columnas = obtener_columnas_modelo(df_train)
    X = df_train[columnas]
    y = df_train[config.TARGET_COLUMN]

    log.info("Entrenamiento | filas=%d | features=%d", len(df_train), len(columnas))

    metricas_dict: dict[str, MetricasModelo] = {}
    modelos = _construir_modelos()

    for nombre, modelo in modelos.items():
        log.info("Evaluando %s con %d-fold CV...", nombre, config.N_FOLDS_CV)
        mae_cv, mae_std = _evaluar_cv(modelo, X, y)

        # Reentrenamiento sobre todo el conjunto para métricas finales
        modelo.fit(X, y)
        train_metrics = _calcular_metricas_train(modelo, X, y)
        importancias = _extraer_feature_importance(modelo, columnas)

        metricas_dict[nombre] = MetricasModelo(
            nombre=nombre,
            mae_cv=round(mae_cv, 4),
            mae_cv_std=round(mae_std, 4),
            r2_train=round(train_metrics["r2_train"], 4),
            rmse_train=round(train_metrics["rmse_train"], 4),
            feature_importance=importancias,
        )

        log.info("  %s | MAE-CV=%.3f (±%.3f) | R²=%.3f | RMSE=%.3f",
                 nombre, mae_cv, mae_std,
                 train_metrics["r2_train"], train_metrics["rmse_train"])

    # Selección por MAE-CV mínimo
    nombre_mejor = min(metricas_dict, key=lambda k: metricas_dict[k].mae_cv)
    modelo_mejor = modelos[nombre_mejor]

    log.info("Modelo seleccionado: %s | MAE-CV=%.3f",
             nombre_mejor, metricas_dict[nombre_mejor].mae_cv)

    resultado = ResultadoModelo(
        nombre_mejor=nombre_mejor,
        modelo_mejor=modelo_mejor,
        columnas_features=columnas,
        metricas=metricas_dict,
    )

    if guardar_metricas:
        guardar_metricas_modelo(resultado)

    return resultado


def guardar_metricas_modelo(resultado: ResultadoModelo,
                              ruta: Path | None = None) -> Path:
    """Persiste las métricas del modelo en JSON.

    Ejemplo:
        >>> guardar_metricas_modelo(resultado)
        PosixPath('.../model_metrics.json')
    """
    ruta = ruta or config.ARCHIVO_METRICAS_MODELO
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(resultado.to_dict(), f, ensure_ascii=False, indent=2)
    log.info("Métricas guardadas en %s", ruta)
    return ruta
