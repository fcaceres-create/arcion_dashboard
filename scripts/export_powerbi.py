"""Exportador de CSVs optimizados para Power BI.

Toma los outputs del pipeline y genera dos CSVs en formato long
con encoding UTF-8 BOM para que Power BI interprete los acentos
correctamente, separador coma, y columnas auxiliares pre-calculadas
para simplificar la creación de medidas DAX.

Uso:
    $ python scripts/export_powerbi.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd  # noqa: E402

from src import config  # noqa: E402
from src.utils import setup_logger  # noqa: E402

log = setup_logger("export_powerbi")


def exportar_para_powerbi() -> None:
    """Lee los outputs del pipeline y genera CSVs listos para Power BI.

    Genera, además de los archivos del pipeline, una versión enriquecida
    con flags y categorías que facilitan filtros y slicers en Power BI.
    """
    if not config.ARCHIVO_PROYECCION_CSV.exists():
        raise FileNotFoundError(
            f"Falta {config.ARCHIVO_PROYECCION_CSV}. "
            f"Ejecutá `python scripts/run_pipeline.py` primero."
        )

    log.info("Leyendo proyección desde %s",
             config.ARCHIVO_PROYECCION_CSV.name)
    df = pd.read_csv(config.ARCHIVO_PROYECCION_CSV, encoding="utf-8-sig")

    # Categorías auxiliares para slicers
    df["Cumple_OMS"] = (df["Tasa_Donacion_x1000"] >= config.OMS_OPTIMO_X1000).astype(int)
    df["Categoria_Cumplimiento"] = pd.cut(
        df["Pct_Cumplimiento_OMS"],
        bins=[0, 50, 70, 85, 100, 200],
        labels=["Crítico", "Bajo", "Medio", "Alto", "Cumple"],
        include_lowest=True,
    ).astype(str)

    # Salida 1: dataset principal
    ruta_pbi = config.RUTA_DATA_OUTPUT / "powerbi_proyeccion.csv"
    df.to_csv(ruta_pbi, index=False, encoding="utf-8-sig")
    log.info("Exportado %s | %d filas", ruta_pbi.name, len(df))

    # Salida 2: tabla de dimensión Provincia
    df_dim_provincia = (
        df[["Provincia", "Region"]]
        .drop_duplicates()
        .sort_values("Provincia")
        .reset_index(drop=True)
    )
    ruta_dim = config.RUTA_DATA_OUTPUT / "powerbi_dim_provincia.csv"
    df_dim_provincia.to_csv(ruta_dim, index=False, encoding="utf-8-sig")
    log.info("Exportado %s | %d filas", ruta_dim.name, len(df_dim_provincia))

    # Salida 3: tabla de dimensión Año
    anios = sorted(df["Año"].unique())
    df_dim_anio = pd.DataFrame({
        "Año": anios,
        "Tipo_Año": ["Histórico" if a <= config.ANIO_FIN_HISTORICO else "Proyectado"
                       for a in anios],
        "Decada": [f"{(a // 10) * 10}s" for a in anios],
    })
    ruta_anio = config.RUTA_DATA_OUTPUT / "powerbi_dim_anio.csv"
    df_dim_anio.to_csv(ruta_anio, index=False, encoding="utf-8-sig")
    log.info("Exportado %s | %d filas", ruta_anio.name, len(df_dim_anio))

    log.info("Exportación a Power BI completa. Archivos en %s",
             config.RUTA_DATA_OUTPUT)


if __name__ == "__main__":
    exportar_para_powerbi()
