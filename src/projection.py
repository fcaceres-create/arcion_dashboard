"""Generación de proyecciones 2025–2030 con escenarios pesimista/base/optimista.

Estrategia:

1. Para cada provincia, partimos de las features observadas en 2024.
2. Proyectamos linealmente las features predictoras hasta 2030 (regresión
   lineal sobre los últimos 5 años de cada variable, con clipping para
   evitar valores absurdos).
3. Aplicamos los ajustes específicos de cada escenario.
4. Predecimos la tasa con el modelo entrenado, año por año, usando
   predicción rolling (la predicción del año t alimenta la lag-1 del t+1).
5. Calculamos donantes absolutos y brecha contra el óptimo OMS.

Ejemplo de uso:
    >>> from src.projection import generar_proyecciones
    >>> df_proy = generar_proyecciones(resultado_modelo, df_features)
    >>> df_proy["Escenario"].unique()
    array(['historico', 'pesimista', 'base', 'optimista'], dtype=object)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config
from src.feature_engineering import construir_features
from src.model import ResultadoModelo
from src.utils import setup_logger

log = setup_logger(__name__)


# Variables que se proyectan linealmente
VARIABLES_A_PROYECTAR = [
    "Población_Total",
    "Población_18_65",
    "Densidad_Poblacional",
    "Pct_Educacion_Superior",
    "Indice_Ingreso_Promedio",
    "Tasa_Desempleo",
    "Pct_Cobertura_Salud",
    "Centros_Hemoterapia",
    "Campañas_Donacion_Anuales",
    "Casos_Dengue_Anual",
    "Casos_VIH_Anual",
    "Medicos",
    "Defunciones_Anuales",
    "Nacimientos_Anuales",
]

# Límites razonables para evitar extrapolaciones absurdas
LIMITES_VARIABLES = {
    "Pct_Educacion_Superior": (5, 60),
    "Tasa_Desempleo": (1, 30),
    "Pct_Cobertura_Salud": (35, 99),
    "Casos_Dengue_Anual": (0, np.inf),
    "Centros_Hemoterapia": (1, np.inf),
    "Campañas_Donacion_Anuales": (1, np.inf),
}


# ---------------------------------------------------------------------
# Proyección de features
# ---------------------------------------------------------------------
def _proyectar_serie(valores: np.ndarray, anios: np.ndarray,
                      anios_futuros: np.ndarray) -> np.ndarray:
    """Ajusta una recta sobre los últimos puntos y extrapola.

    Args:
        valores: Array de valores históricos.
        anios: Array de años correspondientes.
        anios_futuros: Años a proyectar.

    Returns:
        Array con valores proyectados.
    """
    coef = np.polyfit(anios, valores, deg=1)
    return np.polyval(coef, anios_futuros)


def _proyectar_features_provincia(df_prov_hist: pd.DataFrame) -> pd.DataFrame:
    """Construye el panel 2025-2030 para una provincia.

    Args:
        df_prov_hist: Histórico (2015-2024) de UNA provincia.

    Returns:
        DataFrame con filas para 2025-2030 incluyendo features proyectadas.
    """
    provincia = df_prov_hist["Provincia"].iloc[0]
    region = df_prov_hist["Region"].iloc[0]

    # Usamos los últimos 5 años para el ajuste lineal (más estable)
    df_recent = df_prov_hist.tail(5)
    anios_recent = df_recent["Año"].to_numpy()
    anios_futuros = np.array(config.ANIOS_PROYECCION)

    proyecciones = {"Provincia": provincia, "Region": region, "Año": anios_futuros}
    for var in VARIABLES_A_PROYECTAR:
        valores = df_recent[var].to_numpy(dtype=float)
        proyectado = _proyectar_serie(valores, anios_recent, anios_futuros)
        # Clipping defensivo
        if var in LIMITES_VARIABLES:
            lo, hi = LIMITES_VARIABLES[var]
            proyectado = np.clip(proyectado, lo, hi)
        proyecciones[var] = proyectado

    df_fut = pd.DataFrame(proyecciones)
    # Tipos correctos
    cols_enteras = ["Población_Total", "Población_18_65",
                     "Centros_Hemoterapia", "Campañas_Donacion_Anuales",
                     "Casos_Dengue_Anual", "Casos_VIH_Anual", "Medicos",
                     "Defunciones_Anuales", "Nacimientos_Anuales"]
    for col in cols_enteras:
        df_fut[col] = df_fut[col].round().astype(int)

    # Target queda vacío (lo predecirá el modelo)
    df_fut["Tasa_Donacion_x1000"] = np.nan
    df_fut["Donantes_Anuales"] = np.nan
    return df_fut


def proyectar_features_completo(df_historico: pd.DataFrame) -> pd.DataFrame:
    """Genera el panel histórico + proyectado para todas las provincias.

    Args:
        df_historico: Panel con datos 2015-2024 cargado desde el Excel maestro.

    Returns:
        Panel concatenado 2015-2030 (sin target en 2025-2030).
    """
    paneles = []
    for provincia in df_historico["Provincia"].unique():
        df_prov = df_historico[df_historico["Provincia"] == provincia]
        df_fut = _proyectar_features_provincia(df_prov)
        paneles.append(pd.concat([df_prov, df_fut], ignore_index=True))
    df_completo = pd.concat(paneles, ignore_index=True)
    log.info("Features proyectadas | total=%d filas (hist+fut)", len(df_completo))
    return df_completo


# ---------------------------------------------------------------------
# Escenarios y predicción rolling
# ---------------------------------------------------------------------
def _aplicar_ajustes_escenario(df: pd.DataFrame, escenario: str) -> pd.DataFrame:
    """Aplica los multiplicadores propios de cada escenario.

    Solo modifica las filas de proyección (Año >= 2025).

    Args:
        df: DataFrame con features + target.
        escenario: 'pesimista', 'base' u 'optimista'.

    Returns:
        DataFrame con ajustes aplicados (copia).
    """
    df = df.copy()
    ajustes = config.AJUSTES_ESCENARIO.get(escenario, {})
    if not ajustes:
        return df

    mask_futuro = df["Año"] >= config.ANIO_INICIO_PROYECCION
    for variable, ajuste in ajustes.items():
        if variable not in df.columns:
            log.warning("Variable %s no encontrada para escenario %s",
                        variable, escenario)
            continue
        # Promovemos a float para que el factor multiplicativo no genere
        # FutureWarning al asignar resultado decimal sobre columna int.
        df[variable] = df[variable].astype(float)
        df.loc[mask_futuro, variable] = df.loc[mask_futuro, variable] * (1 + ajuste)
        # Clipping defensivo si corresponde
        if variable in LIMITES_VARIABLES:
            lo, hi = LIMITES_VARIABLES[variable]
            df.loc[mask_futuro, variable] = df.loc[mask_futuro, variable].clip(lo, hi)
    return df


def _predecir_rolling(modelo, columnas: list[str],
                       df_panel: pd.DataFrame) -> pd.DataFrame:
    """Predice año a año, propagando la tasa predicha como Lag1 del siguiente.

    Args:
        modelo: Modelo entrenado.
        columnas: Columnas de features esperadas.
        df_panel: Panel completo con features (incluye 2015-2030).

    Returns:
        DataFrame con la columna ``Tasa_Donacion_x1000`` completada.
    """
    df = df_panel.sort_values(["Provincia", "Año"]).copy()

    # Reconstruimos features (incluye Lag1 ya imputada para histórico)
    df = construir_features(df, incluir_lag=True)

    # Iteramos por año dentro del período de proyección
    for anio in config.ANIOS_PROYECCION:
        mask = df["Año"] == anio
        if not mask.any():
            continue
        X_anio = df.loc[mask, columnas]
        pred = modelo.predict(X_anio)
        # Aseguramos rango plausible (no negativos, no absurdamente altos)
        pred = np.clip(pred, 5.0, 40.0)
        df.loc[mask, "Tasa_Donacion_x1000"] = pred

        # Propagamos la predicción al lag-1 del año siguiente
        anio_siguiente = anio + 1
        mask_sig = df["Año"] == anio_siguiente
        if mask_sig.any():
            df_sig = df.loc[mask_sig].sort_values("Provincia")
            df_act = df.loc[mask].sort_values("Provincia")
            df.loc[df_sig.index, "Tasa_Donacion_Lag1"] = df_act["Tasa_Donacion_x1000"].to_numpy()

    # Recalculamos donantes absolutos
    df["Donantes_Anuales"] = (
        df["Tasa_Donacion_x1000"] * df["Población_Total"] / 1000
    ).round().astype(int)
    return df


# ---------------------------------------------------------------------
# Función pública principal
# ---------------------------------------------------------------------
def generar_proyecciones(resultado_modelo: ResultadoModelo,
                            df_panel_completo: pd.DataFrame) -> pd.DataFrame:
    """Genera el dataset final long format con los 3 escenarios.

    Args:
        resultado_modelo: Objeto retornado por ``model.entrenar_y_seleccionar``.
        df_panel_completo: Panel histórico + features futuras proyectadas.

    Returns:
        DataFrame en formato long: una fila por provincia × año × escenario,
        con columnas adicionales de brecha y % cumplimiento OMS.

    Ejemplo:
        >>> df_proy = generar_proyecciones(resultado, df_completo)
        >>> df_proy.columns.tolist()
        [..., 'Escenario', 'Donantes_OMS_Necesarios', 'Brecha_Donantes', ...]
    """
    modelo = resultado_modelo.modelo_mejor
    columnas = resultado_modelo.columnas_features

    log.info("Generando proyecciones con modelo %s | escenarios=%s",
             resultado_modelo.nombre_mejor, list(config.ESCENARIOS))

    paneles_escenario: list[pd.DataFrame] = []

    # Histórico (sin escenario, una sola vez)
    df_hist = df_panel_completo[
        df_panel_completo["Año"] <= config.ANIO_FIN_HISTORICO
    ].copy()
    df_hist["Escenario"] = "historico"
    paneles_escenario.append(df_hist)

    # Cada escenario
    for escenario in config.ESCENARIOS:
        df_aj = _aplicar_ajustes_escenario(df_panel_completo, escenario)
        df_pred = _predecir_rolling(modelo, columnas, df_aj)
        df_fut = df_pred[df_pred["Año"] >= config.ANIO_INICIO_PROYECCION].copy()
        df_fut["Escenario"] = escenario
        paneles_escenario.append(df_fut)

    df_long = pd.concat(paneles_escenario, ignore_index=True)

    # --- Cálculos derivados (brecha vs OMS) ---
    df_long["Donantes_OMS_Necesarios"] = (
        config.OMS_OPTIMO_X1000 * df_long["Población_Total"] / 1000
    ).round().astype(int)

    df_long["Brecha_Donantes"] = (
        df_long["Donantes_OMS_Necesarios"] - df_long["Donantes_Anuales"]
    )

    df_long["Pct_Cumplimiento_OMS"] = (
        df_long["Tasa_Donacion_x1000"] / config.OMS_OPTIMO_X1000 * 100
    ).round(2)

    df_long["Tipo_Año"] = np.where(
        df_long["Año"] <= config.ANIO_FIN_HISTORICO, "Histórico", "Proyectado"
    )

    # Selección y orden de columnas finales para Power BI
    columnas_finales = [
        "Provincia", "Region", "Año", "Tipo_Año", "Escenario",
        "Población_Total", "Población_18_65",
        "Tasa_Donacion_x1000", "Donantes_Anuales",
        "Donantes_OMS_Necesarios", "Brecha_Donantes",
        "Pct_Cumplimiento_OMS",
        "Pct_Educacion_Superior", "Tasa_Desempleo",
        "Centros_Hemoterapia", "Campañas_Donacion_Anuales",
        "Casos_Dengue_Anual",
    ]
    df_long = df_long[columnas_finales].sort_values(
        ["Provincia", "Escenario", "Año"]
    ).reset_index(drop=True)

    log.info("Proyección completa | filas=%d | escenarios=%s",
             len(df_long), df_long["Escenario"].unique().tolist())
    return df_long


def construir_resumen_nacional(df_long: pd.DataFrame) -> pd.DataFrame:
    """Agrega la proyección por año y escenario a nivel país.

    Útil para el dashboard nacional y para reportar al Ministerio.

    Ejemplo:
        >>> df_nac = construir_resumen_nacional(df_proy)
        >>> df_nac.columns.tolist()
        ['Año', 'Escenario', 'Población_Total', ...]
    """
    df = df_long.copy()
    resumen = df.groupby(["Año", "Escenario"], as_index=False).agg(
        Población_Total=("Población_Total", "sum"),
        Donantes_Anuales=("Donantes_Anuales", "sum"),
        Donantes_OMS_Necesarios=("Donantes_OMS_Necesarios", "sum"),
    )
    resumen["Tasa_Nacional_x1000"] = (
        resumen["Donantes_Anuales"] / resumen["Población_Total"] * 1000
    ).round(2)
    resumen["Brecha_Donantes"] = (
        resumen["Donantes_OMS_Necesarios"] - resumen["Donantes_Anuales"]
    )
    resumen["Pct_Cumplimiento_OMS"] = (
        resumen["Tasa_Nacional_x1000"] / config.OMS_OPTIMO_X1000 * 100
    ).round(2)
    return resumen.sort_values(["Escenario", "Año"]).reset_index(drop=True)
