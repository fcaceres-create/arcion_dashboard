"""Pipeline orquestado end-to-end.

Ejecuta secuencialmente:

1. Generación / carga del dataset maestro.
2. Validación de calidad.
3. Construcción de features.
4. Entrenamiento y selección de modelo.
5. Generación de proyecciones (3 escenarios).
6. Exportación a CSV (long format) y resumen nacional.

Uso:
    $ python scripts/run_pipeline.py
    $ python scripts/run_pipeline.py --regenerar-dataset

Salida:
    - data/output/proyeccion_donantes_2030.csv
    - data/output/resumen_nacional.csv
    - data/output/model_metrics.json
    - logs/pipeline.log
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# Permite ejecutar el script desde cualquier directorio
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from src import config  # noqa: E402
from src.data_generator import generar_dataset_maestro  # noqa: E402
from src.data_loader import (  # noqa: E402
    cargar_dataset_maestro, reportar_calidad, separar_historico_proyeccion,
)
from src.data_merger import (  # noqa: E402
    enriquecer_con_refes, enriquecer_con_todas_las_fuentes,
    reporte_cobertura_completo, reporte_cobertura_refes,
)
from src.feature_engineering import construir_features  # noqa: E402
from src.model import entrenar_y_seleccionar  # noqa: E402
from src.projection import (  # noqa: E402
    construir_resumen_nacional, generar_proyecciones, proyectar_features_completo,
)
from src.utils import setup_logger  # noqa: E402

log = setup_logger("pipeline")


def _exportar_csv_utf8_bom(df, ruta: Path) -> None:
    """Escribe CSV con BOM UTF-8 para que Power BI respete los acentos."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(ruta, index=False, encoding="utf-8-sig")
    log.info("Exportado %s | filas=%d", ruta.name, len(df))


def ejecutar_pipeline(regenerar_dataset: bool = False,
                         usar_refes: bool = False,
                         usar_fuentes_reales: bool = False) -> dict:
    """Corre el pipeline completo.

    Args:
        regenerar_dataset: Si True, regenera el Excel sintético desde cero
            aunque ya exista en disco.
        usar_refes: Si True, solo aplica REFES (Capa 1).
        usar_fuentes_reales: Si True, aplica TODAS las capas (REFES +
            Dengue + VIH + Médicos + Defunciones + Nacimientos). Toma
            precedencia sobre ``usar_refes``.

    Returns:
        Diccionario con paths de outputs y métricas resumidas.
    """
    t0 = time.perf_counter()
    modo = ("FUENTES_REALES (1+2+3)" if usar_fuentes_reales
            else "REFES (Capa 1)" if usar_refes else "sintético")
    log.info("=" * 70)
    log.info("PIPELINE | Proyección Donantes Argentina 2030")
    log.info("Modo: %s", modo)
    log.info("=" * 70)

    # 1. Dataset
    if regenerar_dataset or not config.ARCHIVO_DATASET_MAESTRO.exists():
        log.info("[1/6] Generando dataset sintético...")
        generar_dataset_maestro()
    else:
        log.info("[1/6] Dataset existente detectado: %s",
                 config.ARCHIVO_DATASET_MAESTRO.name)

    # 2. Carga + calidad
    log.info("[2/6] Cargando y validando dataset...")
    df_maestro = cargar_dataset_maestro()
    reporte = reportar_calidad(df_maestro)
    log.info("Reporte de calidad: %s", reporte)

    fuente_centros: dict | None = None
    if usar_fuentes_reales:
        log.info("[2.5/6] Enriqueciendo con TODAS las fuentes oficiales...")
        df_maestro = enriquecer_con_todas_las_fuentes(df_maestro)
        fuente_centros = df_maestro["Fuente_Centros_Hemoterapia"].value_counts().to_dict() \
            if "Fuente_Centros_Hemoterapia" in df_maestro.columns \
            else df_maestro.get("Fuente_Centros", pd.Series(dtype=str)).value_counts().to_dict()
        reporte_cob = reporte_cobertura_completo(df_maestro)
        ruta_reporte = config.RUTA_DATA_OUTPUT / "cobertura_fuentes.csv"
        reporte_cob.to_csv(ruta_reporte, index=False, encoding="utf-8-sig")
        log.info("Reporte de cobertura completo guardado en %s",
                 ruta_reporte.name)
    elif usar_refes:
        log.info("[2.5/6] Enriqueciendo con datos REFES (Capa 1)...")
        df_maestro = enriquecer_con_refes(df_maestro)
        fuente_centros = df_maestro["Fuente_Centros"].value_counts().to_dict()
        reporte_cob = reporte_cobertura_refes(df_maestro)
        ruta_reporte = config.RUTA_DATA_OUTPUT / "cobertura_refes.csv"
        reporte_cob.to_csv(ruta_reporte, index=False, encoding="utf-8-sig")
        log.info("Reporte de cobertura REFES guardado en %s", ruta_reporte.name)

    # 3. Histórico para entrenamiento
    log.info("[3/6] Construyendo features...")
    df_hist, _ = separar_historico_proyeccion(df_maestro)
    df_hist_features = construir_features(df_hist, incluir_lag=True)

    # 4. Modelo
    log.info("[4/6] Entrenando modelos...")
    resultado = entrenar_y_seleccionar(df_hist_features)

    # 5. Proyecciones (sobre histórico + features futuras proyectadas)
    log.info("[5/6] Generando proyecciones 2025-2030...")
    df_panel_completo = proyectar_features_completo(df_hist)
    df_proyeccion = generar_proyecciones(resultado, df_panel_completo)
    df_resumen = construir_resumen_nacional(df_proyeccion)

    # 6. Exportación
    log.info("[6/6] Exportando outputs...")
    _exportar_csv_utf8_bom(df_proyeccion, config.ARCHIVO_PROYECCION_CSV)
    _exportar_csv_utf8_bom(df_resumen, config.ARCHIVO_RESUMEN_NACIONAL)

    duracion = time.perf_counter() - t0
    log.info("=" * 70)
    log.info("PIPELINE FINALIZADO en %.2fs", duracion)
    log.info("Modelo ganador: %s | MAE-CV=%.3f",
             resultado.nombre_mejor,
             resultado.metricas[resultado.nombre_mejor].mae_cv)
    log.info("=" * 70)

    return {
        "modelo": resultado.nombre_mejor,
        "mae_cv": resultado.metricas[resultado.nombre_mejor].mae_cv,
        "duracion_seg": round(duracion, 2),
        "archivo_proyeccion": str(config.ARCHIVO_PROYECCION_CSV),
        "archivo_resumen": str(config.ARCHIVO_RESUMEN_NACIONAL),
        "fuente_centros": fuente_centros,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pipeline de proyección de donantes.")
    parser.add_argument(
        "--regenerar-dataset", action="store_true",
        help="Forzar regeneración del Excel sintético.",
    )
    parser.add_argument(
        "--usar-refes", action="store_true",
        help="Solo Capa 1: REFES (centros de hemoterapia).",
    )
    parser.add_argument(
        "--fuentes-reales", action="store_true",
        help="TODAS las capas: REFES + Dengue + VIH + Médicos + Vitales.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    resumen = ejecutar_pipeline(
        regenerar_dataset=args.regenerar_dataset,
        usar_refes=args.usar_refes,
        usar_fuentes_reales=args.fuentes_reales,
    )
    print("\n=== Resumen ===")
    for k, v in resumen.items():
        print(f"  {k}: {v}")
