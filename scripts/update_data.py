"""Script para refrescar variables externas desde APIs públicas.

Descarga indicadores demográficos y socioeconómicos de Argentina
desde el Banco Mundial y datos.gob.ar, y guarda los resultados en
``data/processed/`` para alimentar futuras versiones del modelo
con datos reales (cuando reemplacemos el dataset sintético).

Uso:
    $ python scripts/update_data.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import config  # noqa: E402
from src.api_clients import DatosGobArClient, WorldBankClient  # noqa: E402
from src.utils import setup_logger  # noqa: E402

log = setup_logger("update_data")


# Indicadores del Banco Mundial relevantes para el proyecto
INDICADORES_WB = {
    "SP.POP.TOTL":         "Población total",
    "SP.POP.1564.TO.ZS":   "% Población 15-64",
    "SE.TER.ENRR":         "Matrícula educación terciaria (% bruto)",
    "SL.UEM.TOTL.ZS":      "Tasa de desempleo (% fuerza laboral)",
    "SH.XPD.CHEX.GD.ZS":   "Gasto en salud (% PBI)",
    "SH.MED.PHYS.ZS":      "Médicos por cada 1000 hab",
}


def descargar_indicadores_wb() -> None:
    """Descarga todos los indicadores del Banco Mundial y los guarda en CSV."""
    cli = WorldBankClient()
    for codigo, descripcion in INDICADORES_WB.items():
        log.info("Descargando WB | %s — %s", codigo, descripcion)
        df = cli.obtener_indicador(codigo,
                                      anio_inicio=config.ANIO_INICIO_HISTORICO,
                                      anio_fin=config.ANIO_FIN_HISTORICO)
        if df is None or df.empty:
            log.warning("Sin datos para %s", codigo)
            continue
        ruta = config.RUTA_DATA_PROCESSED / f"wb_{codigo.replace('.', '_')}.csv"
        df.to_csv(ruta, index=False, encoding="utf-8-sig")
        log.info("  → %s", ruta.name)


def descargar_series_datosgobar() -> None:
    """Descarga series de tiempo argentinas de interés.

    Por defecto descarga el Estimador Mensual de Actividad Económica (EMAE)
    como ejemplo. Cuando se identifiquen los IDs específicos del Plan
    Nacional de Sangre, agregarlos a ``SERIES_INTERES``.
    """
    cli = DatosGobArClient()
    SERIES_INTERES = {
        "143.3_NO_PR_2004_A_21": "EMAE - serie original (referencia)",
    }
    for id_serie, descripcion in SERIES_INTERES.items():
        log.info("Descargando datos.gob.ar | %s — %s", id_serie, descripcion)
        df = cli.obtener_serie(id_serie)
        if df is None or df.empty:
            log.warning("Sin datos para %s", id_serie)
            continue
        ruta = config.RUTA_DATA_PROCESSED / f"datosgobar_{id_serie}.csv"
        df.to_csv(ruta, index=False, encoding="utf-8-sig")
        log.info("  → %s", ruta.name)


if __name__ == "__main__":
    log.info("Actualizando datos externos...")
    descargar_indicadores_wb()
    descargar_series_datosgobar()
    log.info("Actualización completa.")
