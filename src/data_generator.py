"""Generador de dataset sintético de donantes de sangre por provincia.

Crea un Excel maestro con 4 hojas (Diccionario, Datos, Resumen_Nacional,
Notas metodológicas) que se utiliza como reemplazo temporal hasta obtener
los datos oficiales del Plan Nacional de Sangre.

Características del dataset:

- 24 jurisdicciones argentinas con poblaciones del Censo INDEC 2022.
- 16 años (2015–2030); el target solo está cargado para 2015–2024.
- Caída por pandemia COVID en 2020-2021 (~ -15% en tasa de donación).
- Variación regional realista (Centro/Patagonia más altas que NEA/NOA).
- Tasa promedio nacional calibrada a ~19/1000 (línea base OPS 2023).

Ejemplo de uso:
    >>> from src.data_generator import generar_dataset_maestro
    >>> ruta = generar_dataset_maestro()
    >>> print(f"Dataset creado en: {ruta}")
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from src import config
from src.utils import setup_logger

log = setup_logger(__name__)


# ---------------------------------------------------------------------
# Generadores auxiliares de variables socioeconómicas
# ---------------------------------------------------------------------
def _generar_serie_temporal(valor_inicial: float,
                             tasa_cambio_anual: float,
                             ruido: float,
                             n_anios: int,
                             rng: np.random.Generator) -> np.ndarray:
    """Genera una serie con crecimiento compuesto + ruido gaussiano.

    Args:
        valor_inicial: Valor en el primer año.
        tasa_cambio_anual: Crecimiento (+) o decrecimiento (-) anual.
        ruido: Desvío estándar del ruido relativo.
        n_anios: Cantidad de años a generar.
        rng: Generador numpy.

    Returns:
        Array de longitud ``n_anios``.

    Ejemplo:
        >>> rng = np.random.default_rng(42)
        >>> _generar_serie_temporal(100, 0.02, 0.01, 10, rng)
    """
    años = np.arange(n_anios)
    base = valor_inicial * np.power(1 + tasa_cambio_anual, años)
    perturbacion = rng.normal(loc=1.0, scale=ruido, size=n_anios)
    return base * perturbacion


def _generar_features_provincia(provincia: str,
                                 datos_prov: dict,
                                 rng: np.random.Generator) -> pd.DataFrame:
    """Genera el panel completo (16 años) para una sola provincia.

    Args:
        provincia: Nombre de la jurisdicción.
        datos_prov: Diccionario con población, región y densidad.
        rng: Generador numpy con semilla fija.

    Returns:
        DataFrame con todas las variables predictoras + target histórico.
    """
    n_total = len(config.TODOS_LOS_ANIOS)
    poblacion_2024 = datos_prov["poblacion_2024"]
    region = datos_prov["region"]
    densidad = datos_prov["densidad"]

    # --- Demografía ---
    # Crecimiento poblacional anual ~0.9% (consistente con proyecciones INDEC)
    pob_2015 = poblacion_2024 / (1.009 ** 9)
    poblacion_total = _generar_serie_temporal(
        pob_2015, 0.009, 0.003, n_total, rng
    ).astype(int)

    # Población en edad de donar (18-65): rango ~63-65% según provincia
    pct_18_65 = rng.uniform(0.63, 0.65)
    poblacion_18_65 = (poblacion_total * pct_18_65).astype(int)

    # Densidad: aprox constante con leve variación
    densidad_serie = densidad * rng.normal(1.0, 0.01, size=n_total)

    # --- Socioeconómicas ---
    # Educación superior: % población con estudios universitarios o terciarios
    base_educ = {"Centro": 22, "Patagonia": 19, "Cuyo": 17, "NOA": 15, "NEA": 13}[region]
    pct_educacion_superior = _generar_serie_temporal(
        base_educ, 0.012, 0.02, n_total, rng
    )

    # Índice de ingreso promedio (escala 0–100, normalizado)
    base_ingreso = {"Centro": 65, "Patagonia": 72, "Cuyo": 55, "NOA": 48, "NEA": 45}[region]
    indice_ingreso = _generar_serie_temporal(
        base_ingreso, 0.008, 0.03, n_total, rng
    )

    # Tasa de desempleo (%)
    base_desempleo = {"Centro": 8, "Patagonia": 6, "Cuyo": 7, "NOA": 9, "NEA": 10}[region]
    tasa_desempleo = _generar_serie_temporal(
        base_desempleo, -0.005, 0.08, n_total, rng
    )
    # Pico por pandemia
    for i, anio in enumerate(config.TODOS_LOS_ANIOS):
        if anio in config.ANIOS_PANDEMIA:
            tasa_desempleo[i] *= 1.35

    # Cobertura de salud (%)
    base_cobertura = {"Centro": 75, "Patagonia": 82, "Cuyo": 70, "NOA": 65, "NEA": 60}[region]
    pct_cobertura_salud = _generar_serie_temporal(
        base_cobertura, 0.005, 0.015, n_total, rng
    ).clip(40, 95)

    # --- Sistema sanitario ---
    # Centros de hemoterapia escalan con población (1 cada ~120k habitantes)
    centros_base = max(2, poblacion_2024 // 120_000)
    centros_hemoterapia = _generar_serie_temporal(
        centros_base * 0.85, 0.02, 0.05, n_total, rng
    ).astype(int).clip(min=1)

    # Campañas de donación anuales: variabilidad alta
    campañas_base = max(3, int(poblacion_2024 / 80_000))
    campañas = _generar_serie_temporal(
        campañas_base, 0.04, 0.15, n_total, rng
    ).astype(int).clip(min=1)
    # Las campañas caen durante pandemia
    for i, anio in enumerate(config.TODOS_LOS_ANIOS):
        if anio in config.ANIOS_PANDEMIA:
            campañas[i] = max(1, int(campañas[i] * 0.5))

    # --- Epidemiológicas ---
    # Casos de dengue: brotes en NEA y NOA, regiones del norte tropical
    multiplicador_dengue = {"Centro": 0.4, "Patagonia": 0.05,
                              "Cuyo": 0.3, "NOA": 1.5, "NEA": 2.2}[region]
    casos_dengue_base = poblacion_2024 / 10_000 * multiplicador_dengue
    casos_dengue = _generar_serie_temporal(
        casos_dengue_base, 0.10, 0.40, n_total, rng
    ).astype(int).clip(min=0)
    # Brote 2023-2024 (efecto histórico real)
    for i, anio in enumerate(config.TODOS_LOS_ANIOS):
        if anio in (2023, 2024):
            casos_dengue[i] = int(casos_dengue[i] * 2.5)

    # --- Target: tasa de donación / 1000 hab ---
    tasa_base_region = config.TASAS_REGIONALES_BASE[region]
    # Modelo subyacente realista: la tasa depende de educación, cobertura,
    # campañas, centros, desempleo (negativo), e incluye ruido y pandemia.
    tasa = (
        tasa_base_region
        + 0.06 * (pct_educacion_superior - base_educ)
        + 0.04 * (pct_cobertura_salud - base_cobertura)
        + 0.012 * (campañas - campañas_base)
        + 0.08 * (centros_hemoterapia - centros_base)
        - 0.18 * (tasa_desempleo - base_desempleo)
        + rng.normal(0, 0.6, size=n_total)
    )
    # Aplicamos efecto pandemia
    for i, anio in enumerate(config.TODOS_LOS_ANIOS):
        if anio in config.ANIOS_PANDEMIA:
            tasa[i] *= (1 + config.IMPACTO_PANDEMIA)
    tasa = np.clip(tasa, 8.0, 35.0)

    # Garantizamos consistencia interna: redondeamos la tasa primero y
    # calculamos los donantes a partir de esa tasa ya redondeada.
    # Si calculáramos donantes con la tasa cruda y guardáramos la
    # redondeada, en provincias grandes (BA, CABA) la divergencia llega
    # a decenas de donantes — incoherente para uso académico.
    tasa = np.round(tasa, 2)
    donantes_anuales = (tasa * poblacion_total / 1000).round().astype(int)

    # --- Construcción del DataFrame ---
    df = pd.DataFrame({
        "Provincia": provincia,
        "Region": region,
        "Año": config.TODOS_LOS_ANIOS,
        "Población_Total": poblacion_total,
        "Población_18_65": poblacion_18_65,
        "Densidad_Poblacional": np.round(densidad_serie, 2),
        "Pct_Educacion_Superior": np.round(pct_educacion_superior, 2),
        "Indice_Ingreso_Promedio": np.round(indice_ingreso, 2),
        "Tasa_Desempleo": np.round(tasa_desempleo, 2),
        "Pct_Cobertura_Salud": np.round(pct_cobertura_salud, 2),
        "Centros_Hemoterapia": centros_hemoterapia,
        "Campañas_Donacion_Anuales": campañas,
        "Casos_Dengue_Anual": casos_dengue,
        "Tasa_Donacion_x1000": tasa,
        "Donantes_Anuales": donantes_anuales,
    })

    # El target solo existe en el período histórico
    mask_proyeccion = df["Año"] > config.ANIO_FIN_HISTORICO
    df.loc[mask_proyeccion, ["Tasa_Donacion_x1000", "Donantes_Anuales"]] = np.nan

    return df


# ---------------------------------------------------------------------
# Construcción del Excel maestro
# ---------------------------------------------------------------------
def _hoja_diccionario() -> pd.DataFrame:
    """Genera la hoja 'Diccionario' con la documentación de cada variable."""
    return pd.DataFrame([
        ("Provincia", "Texto", "—", "Jurisdicción argentina (24 valores).", "INDEC"),
        ("Region", "Texto", "—", "Región geográfica: Centro, NOA, NEA, Cuyo, Patagonia.", "INDEC"),
        ("Año", "Entero", "Año", "Período de medición.", "INDEC"),
        ("Población_Total", "Entero", "habitantes", "Población total estimada.", "INDEC Censo 2022 + proyecciones"),
        ("Población_18_65", "Entero", "habitantes", "Población elegible para donar (18-65 años).", "INDEC EPH"),
        ("Densidad_Poblacional", "Decimal", "hab/km²", "Densidad por jurisdicción.", "INDEC"),
        ("Pct_Educacion_Superior", "Decimal", "%", "Porcentaje con estudios terciarios o universitarios.", "INDEC EPH"),
        ("Indice_Ingreso_Promedio", "Decimal", "índice 0-100", "Índice normalizado de ingreso del hogar.", "INDEC EPH"),
        ("Tasa_Desempleo", "Decimal", "%", "Tasa de desocupación EPH.", "INDEC EPH"),
        ("Pct_Cobertura_Salud", "Decimal", "%", "% de población con obra social o prepaga.", "INDEC EPH"),
        ("Centros_Hemoterapia", "Entero", "unidades", "Cantidad de centros activos.", "Plan Nacional de Sangre"),
        ("Campañas_Donacion_Anuales", "Entero", "unidades", "Campañas oficiales realizadas en el año.", "Plan Nacional de Sangre"),
        ("Casos_Dengue_Anual", "Entero", "casos", "Casos confirmados de dengue.", "BoletínIntegrado de Vigilancia"),
        ("Tasa_Donacion_x1000", "Decimal", "donac/1000 hab", "TARGET — Tasa de donaciones por 1000 hab.", "Plan Nacional de Sangre"),
        ("Donantes_Anuales", "Entero", "personas", "TARGET — Cantidad absoluta de donantes.", "Plan Nacional de Sangre"),
    ], columns=["Variable", "Tipo", "Unidad", "Descripción", "Fuente esperada"])


def _hoja_resumen_nacional(df_datos: pd.DataFrame) -> pd.DataFrame:
    """Calcula agregaciones nacionales por año (solo histórico)."""
    df_hist = df_datos[df_datos["Año"] <= config.ANIO_FIN_HISTORICO].copy()
    resumen = df_hist.groupby("Año", as_index=False).agg(
        Población_Total=("Población_Total", "sum"),
        Donantes_Total=("Donantes_Anuales", "sum"),
        Centros_Total=("Centros_Hemoterapia", "sum"),
        Campañas_Total=("Campañas_Donacion_Anuales", "sum"),
    )
    resumen["Tasa_Nacional_x1000"] = (
        resumen["Donantes_Total"] / resumen["Población_Total"] * 1000
    ).round(2)
    resumen["Brecha_OMS_x1000"] = (
        config.OMS_OPTIMO_X1000 - resumen["Tasa_Nacional_x1000"]
    ).round(2)
    resumen["Pct_Cumplimiento_OMS"] = (
        resumen["Tasa_Nacional_x1000"] / config.OMS_OPTIMO_X1000 * 100
    ).round(1)
    return resumen


def _hoja_notas() -> pd.DataFrame:
    """Documentación metodológica del dataset sintético."""
    notas = [
        "PROYECTO: Proyección de Donantes de Sangre - Argentina 2030",
        "VERSIÓN: 0.1.0 (dataset sintético inicial)",
        "FECHA DE GENERACIÓN: ver propiedades del archivo",
        "",
        "ALCANCE:",
        "  - 24 jurisdicciones argentinas (CABA + 23 provincias).",
        "  - Período histórico: 2015-2024.",
        "  - Período a proyectar (sin target): 2025-2030.",
        "",
        "ADVERTENCIA IMPORTANTE:",
        "  Este dataset es SINTÉTICO. Fue construido para validar el pipeline",
        "  metodológico mientras se obtienen los datos oficiales del Plan Nacional",
        "  de Sangre. NO debe utilizarse para conclusiones epidemiológicas reales.",
        "",
        "SUPUESTOS DE GENERACIÓN:",
        "  - Tasa nacional calibrada a ~19/1000 (línea base OPS 2023).",
        "  - Caída de -15% en tasa durante la pandemia (2020-2021).",
        "  - Tasas regionales heterogéneas (Centro/Patagonia > NOA/NEA).",
        "  - Brote de dengue 2023-2024 modelado con factor 2.5x.",
        "  - Crecimiento poblacional ~0.9% anual según INDEC.",
        "  - Random state fijo (42) para reproducibilidad.",
        "",
        "FUENTES DE DATOS REALES (TARGET):",
        "  - INDEC: Censo Nacional 2022, EPH trimestral.",
        "  - Plan Nacional de Sangre, Ministerio de Salud de la Nación.",
        "  - OPS/PAHO: Suministro de sangre LATAM, reporte 2023.",
        "  - World Bank Open Data API.",
        "  - Boletín Integrado de Vigilancia (Min. Salud).",
        "",
        "META OMS:",
        f"  30 donaciones / 1000 habitantes (autosuficiencia hemoterápica).",
    ]
    return pd.DataFrame({"Nota": notas})


def generar_dataset_maestro(ruta_destino: Path | None = None,
                             semilla: int | None = None) -> Path:
    """Genera el Excel maestro con las 4 hojas requeridas.

    Args:
        ruta_destino: Path del Excel a crear. Si es ``None`` usa config.
        semilla: Semilla del generador. Si es ``None`` usa ``RANDOM_STATE``.

    Returns:
        Path del archivo creado.

    Ejemplo:
        >>> ruta = generar_dataset_maestro()
        >>> ruta.exists()
        True
    """
    ruta_destino = ruta_destino or config.ARCHIVO_DATASET_MAESTRO
    semilla = semilla if semilla is not None else config.RANDOM_STATE

    log.info("Generando dataset sintético | semilla=%s", semilla)
    rng = np.random.default_rng(semilla)

    paneles = []
    for provincia, datos_prov in config.PROVINCIAS_ARGENTINA.items():
        log.debug("  Generando panel para %s", provincia)
        paneles.append(_generar_features_provincia(provincia, datos_prov, rng))

    df_datos = pd.concat(paneles, ignore_index=True)
    log.info("Panel construido: %d filas × %d columnas",
             len(df_datos), len(df_datos.columns))

    df_diccionario = _hoja_diccionario()
    df_resumen = _hoja_resumen_nacional(df_datos)
    df_notas = _hoja_notas()

    ruta_destino.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(ruta_destino, engine="xlsxwriter") as writer:
        df_diccionario.to_excel(writer, sheet_name="Diccionario", index=False)
        df_datos.to_excel(writer, sheet_name="Datos", index=False)
        df_resumen.to_excel(writer, sheet_name="Resumen_Nacional", index=False)
        df_notas.to_excel(writer, sheet_name="Notas_Metodologicas", index=False)

        # Formato visual básico para que el Excel sea presentable
        wb = writer.book
        formato_header = wb.add_format({
            "bold": True, "bg_color": "#B71C1C", "font_color": "white",
            "border": 1, "align": "center", "valign": "vcenter",
        })
        formato_numero = wb.add_format({"num_format": "#,##0"})
        formato_decimal = wb.add_format({"num_format": "#,##0.00"})

        for nombre_hoja, df_hoja in [("Diccionario", df_diccionario),
                                       ("Datos", df_datos),
                                       ("Resumen_Nacional", df_resumen),
                                       ("Notas_Metodologicas", df_notas)]:
            ws = writer.sheets[nombre_hoja]
            for col_idx, col_nombre in enumerate(df_hoja.columns):
                ws.write(0, col_idx, col_nombre, formato_header)
                # Anchos automáticos básicos
                ancho = max(len(str(col_nombre)),
                            int(df_hoja[col_nombre].astype(str).str.len().max()
                                if len(df_hoja) else 12))
                ws.set_column(col_idx, col_idx, min(ancho + 2, 35))
            ws.freeze_panes(1, 0)

    log.info("Dataset maestro guardado en: %s", ruta_destino)
    return ruta_destino


if __name__ == "__main__":
    # Ejecución directa para regenerar el dataset desde la línea de comandos.
    generar_dataset_maestro()
