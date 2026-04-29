"""Cruce entre dataset maestro y fuentes oficiales externas.

Este módulo es la capa de integración entre las variables sintéticas
del dataset maestro y los datos reales descargados de portales públicos
(actualmente: REFES del Ministerio de Salud).

Estrategia general:

1. **Fuente real preferida**: cuando una fuente externa aporta dato real
   para una combinación (provincia, año), reemplaza al sintético.
2. **Fallback sintético**: cuando la fuente externa no tiene cobertura
   (provincia huérfana, año sin snapshot), se mantiene el valor sintético
   y se marca con una columna ``Fuente_<Variable>`` para trazabilidad.
3. **Interpolación temporal**: para años sin snapshot REFES (ej. 2023),
   interpolamos linealmente entre los snapshots vecinos por provincia.

Esta separación es importante para la **defensa académica**: cualquier
fila del dataset final puede rastrearse a su fuente original.

Ejemplo de uso:
    >>> from src.data_loader import cargar_dataset_maestro
    >>> from src.data_merger import enriquecer_con_refes
    >>> df = cargar_dataset_maestro()
    >>> df_enriquecido = enriquecer_con_refes(df)
    >>> df_enriquecido[['Provincia','Año','Centros_Hemoterapia','Fuente_Centros']].head()
"""
from __future__ import annotations

import pandas as pd

from src import config
from src.api_clients import DatosSaludArClient
from src.utils import setup_logger

log = setup_logger(__name__)


# Años para los que intentaremos pedir snapshot REFES.
# El cliente elige el más cercano si no hay exacto.
ANIOS_REFES_OBJETIVO = list(range(
    config.ANIO_INICIO_HISTORICO, config.ANIO_FIN_HISTORICO + 1
))


def descargar_panel_refes(
    cliente: DatosSaludArClient | None = None,
    anios: list[int] = ANIOS_REFES_OBJETIVO,
) -> pd.DataFrame:
    """Construye el panel completo (Provincia × Año) de centros REFES.

    Llama al cliente CKAN para cada año, agrega por provincia, y luego
    interpola los gaps temporales por provincia (típicamente 2023).

    Args:
        cliente: Cliente ya instanciado (para test/mock); si es None se crea uno.
        anios: Años a cubrir (por defecto el período histórico completo).

    Returns:
        DataFrame con columnas
        ``[Provincia, Año, Centros_Hemoterapia_REFES, Snapshot_REFES_Anio]``.

    Ejemplo:
        >>> df = descargar_panel_refes()
        >>> df.shape
        (240, 4)
    """
    cliente = cliente or DatosSaludArClient()
    paneles: list[pd.DataFrame] = []

    # Identificamos qué snapshots existen realmente (evitamos volver a llamar
    # a la API una vez por año cuando el cliente devolvería el mismo recurso).
    recursos = cliente.listar_recursos_refes() or []
    anios_disponibles = sorted({
        r.get("anio_inferido")
        for r in recursos
        if r.get("anio_inferido") and r.get("format") in ("CSV", "XLSX", "XLS")
    })
    log.info("Snapshots REFES disponibles: %s", anios_disponibles)

    # Descargamos cada snapshot disponible (no uno por año pedido)
    for anio in anios_disponibles:
        if anio < min(anios) - 3 or anio > max(anios) + 3:
            continue  # ignoramos años muy fuera del rango de interés
        df_anio = cliente.obtener_centros_hemoterapia_por_provincia(anio)
        if df_anio is None or df_anio.empty:
            continue
        df_anio = df_anio.rename(
            columns={"Centros_Hemoterapia": "Centros_Hemoterapia_REFES"}
        )
        df_anio["Snapshot_REFES_Anio"] = anio
        paneles.append(df_anio)

    if not paneles:
        log.warning("No se obtuvo ningún snapshot REFES")
        return pd.DataFrame(
            columns=["Provincia", "Año", "Centros_Hemoterapia_REFES",
                     "Snapshot_REFES_Anio"]
        )

    df_real = pd.concat(paneles, ignore_index=True)

    # Expandimos al panel completo Provincia × Año pedido, interpolando
    return _interpolar_panel_provincial(df_real, anios)


def _interpolar_panel_provincial(df_real: pd.DataFrame,
                                    anios_objetivo: list[int]) -> pd.DataFrame:
    """Rellena gaps temporales por provincia con interpolación lineal.

    Args:
        df_real: Panel observado (puede tener gaps).
        anios_objetivo: Lista de años deseados en el output.

    Returns:
        Panel completo con todas las combinaciones (Provincia, año_objetivo).
        ``Snapshot_REFES_Anio`` queda con el snapshot más cercano usado.
    """
    provincias = sorted(df_real["Provincia"].unique())
    if not provincias:
        return df_real

    # Producto cartesiano provincia × año_objetivo
    indice_completo = pd.MultiIndex.from_product(
        [provincias, anios_objetivo], names=["Provincia", "Año"]
    )
    base = pd.DataFrame(index=indice_completo).reset_index()

    # Merge con observados
    df = base.merge(df_real, how="left", on=["Provincia", "Año"])

    # Interpolación por provincia (lineal, manteniendo extremos)
    df = df.sort_values(["Provincia", "Año"]).copy()
    df["Centros_Hemoterapia_REFES"] = (
        df.groupby("Provincia")["Centros_Hemoterapia_REFES"]
        .transform(lambda s: s.interpolate(method="linear", limit_direction="both"))
    )
    # Si quedaran nulos (provincia con 0 observaciones), los dejamos NaN
    # — el caller decidirá fallback.
    df["Centros_Hemoterapia_REFES"] = df["Centros_Hemoterapia_REFES"].round()
    return df


def enriquecer_con_refes(df_maestro: pd.DataFrame,
                            cliente: DatosSaludArClient | None = None,
                            ) -> pd.DataFrame:
    """Reemplaza ``Centros_Hemoterapia`` con datos REFES cuando es posible.

    Política de fusión:
        - Si REFES tiene un valor > 0 para (provincia, año), se usa ese.
        - Si REFES es 0 o NaN (provincia sin servicios identificables o
          año fuera del rango de snapshots), se mantiene el valor sintético.
        - Se agrega ``Fuente_Centros`` con valores 'REFES' o 'sintetico'
          para trazabilidad académica.

    Args:
        df_maestro: Panel completo del dataset maestro.
        cliente: Cliente CKAN (para test/mock).

    Returns:
        Copia del DataFrame con la columna ``Centros_Hemoterapia``
        actualizada y una nueva columna ``Fuente_Centros``.

    Ejemplo:
        >>> df_enr = enriquecer_con_refes(df_maestro)
        >>> df_enr['Fuente_Centros'].value_counts()
        sintetico    240
        REFES        144
        Name: Fuente_Centros, dtype: int64
    """
    log.info("Enriqueciendo dataset maestro con REFES...")
    df = df_maestro.copy()

    panel_refes = descargar_panel_refes(cliente)

    if panel_refes.empty:
        log.warning("REFES no aportó datos. Se mantiene íntegramente el dataset sintético.")
        df["Fuente_Centros"] = "sintetico"
        return df

    # Merge por (Provincia, Año)
    df = df.merge(
        panel_refes[["Provincia", "Año", "Centros_Hemoterapia_REFES"]],
        on=["Provincia", "Año"], how="left",
    )

    # Política de reemplazo: REFES > 0 manda; si es 0 o NaN, sintético gana.
    es_real = (df["Centros_Hemoterapia_REFES"].fillna(0) > 0)
    df["Fuente_Centros"] = "sintetico"
    df.loc[es_real, "Fuente_Centros"] = "REFES"

    df["Centros_Hemoterapia"] = df["Centros_Hemoterapia_REFES"].where(
        es_real, df["Centros_Hemoterapia"]
    ).astype(int)

    df = df.drop(columns=["Centros_Hemoterapia_REFES"])

    # Reporte de cobertura
    cobertura = df.groupby("Fuente_Centros").size().to_dict()
    log.info("Cobertura post-merge | %s", cobertura)
    pct_real = cobertura.get("REFES", 0) / len(df) * 100
    log.info("Filas con dato REFES real: %.1f%% | resto sintético", pct_real)

    return df


def _enriquecer_columna_anio_provincia(
    df_maestro: pd.DataFrame,
    df_real: pd.DataFrame,
    columna_destino: str,
    columna_real: str,
    nombre_fuente: str,
) -> pd.DataFrame:
    """Helper genérico: reemplaza una columna usando datos reales por (Provincia, Año).

    Args:
        df_maestro: Panel maestro a enriquecer.
        df_real: DataFrame con columnas ``[Provincia, Año, columna_real]``.
        columna_destino: Nombre de la columna en df_maestro a sobrescribir.
        columna_real: Nombre de la columna en df_real con el valor.
        nombre_fuente: Etiqueta para la columna ``Fuente_<destino>``.

    Returns:
        Copia de df_maestro con columna actualizada y trazabilidad.
    """
    df = df_maestro.copy()
    fuente_col = f"Fuente_{columna_destino}"

    if df_real is None or df_real.empty:
        log.warning("Sin datos reales para %s — todo queda sintético",
                    columna_destino)
        if fuente_col not in df.columns:
            df[fuente_col] = "sintetico"
        return df

    df = df.merge(
        df_real[["Provincia", "Año", columna_real]].rename(
            columns={columna_real: f"__{columna_real}_real"}
        ),
        on=["Provincia", "Año"], how="left",
    )
    es_real = df[f"__{columna_real}_real"].notna() & (
        df[f"__{columna_real}_real"] > 0
    )
    df[fuente_col] = "sintetico"
    df.loc[es_real, fuente_col] = nombre_fuente
    df[columna_destino] = df[f"__{columna_real}_real"].where(
        es_real, df[columna_destino]
    ).round().astype(int)
    df = df.drop(columns=[f"__{columna_real}_real"])

    cobertura = df[fuente_col].value_counts().to_dict()
    log.info("Cobertura %s | %s", columna_destino, cobertura)
    return df


def enriquecer_con_dengue(df_maestro: pd.DataFrame,
                              cliente: DatosSaludArClient | None = None,
                              ) -> pd.DataFrame:
    """Reemplaza ``Casos_Dengue_Anual`` con datos reales de vigilancia."""
    cliente = cliente or DatosSaludArClient()
    log.info("Capa 2 | Enriqueciendo con casos reales de Dengue...")
    df_real = cliente.obtener_casos_dengue_por_provincia_anio()
    return _enriquecer_columna_anio_provincia(
        df_maestro, df_real,
        columna_destino="Casos_Dengue_Anual",
        columna_real="Casos_Dengue",
        nombre_fuente="Vigilancia_Dengue",
    )


def enriquecer_con_vih(df_maestro: pd.DataFrame,
                          cliente: DatosSaludArClient | None = None,
                          ) -> pd.DataFrame:
    """Reemplaza ``Casos_VIH_Anual`` con datos reales del Plan Nacional VIH."""
    cliente = cliente or DatosSaludArClient()
    log.info("Capa 2 | Enriqueciendo con casos reales de VIH...")
    df_real = cliente.obtener_casos_vih_por_provincia_anio()
    return _enriquecer_columna_anio_provincia(
        df_maestro, df_real,
        columna_destino="Casos_VIH_Anual",
        columna_real="Casos_VIH",
        nombre_fuente="VIH_MinSalud",
    )


def enriquecer_con_medicos(df_maestro: pd.DataFrame,
                              cliente: DatosSaludArClient | None = None,
                              ) -> pd.DataFrame:
    """Reemplaza ``Medicos`` con el snapshot oficial (DISCONTINUADO 2019).

    Como el snapshot no varía con el año, replicamos el valor para todos
    los años de cada provincia.
    """
    cliente = cliente or DatosSaludArClient()
    log.info("Capa 3 | Enriqueciendo con cantidad real de Médicos...")
    df_real = cliente.obtener_medicos_por_provincia()
    if df_real is None or df_real.empty:
        df_maestro = df_maestro.copy()
        df_maestro["Fuente_Medicos"] = "sintetico"
        return df_maestro

    # Replicamos el snapshot a todos los años para hacer un merge limpio
    anios = df_maestro["Año"].unique()
    df_real_anual = pd.concat([
        df_real.assign(Año=a) for a in anios
    ], ignore_index=True)

    return _enriquecer_columna_anio_provincia(
        df_maestro, df_real_anual,
        columna_destino="Medicos",
        columna_real="Medicos",
        nombre_fuente="MinSalud_RRHH",
    )


def enriquecer_con_defunciones(df_maestro: pd.DataFrame,
                                   cliente: DatosSaludArClient | None = None,
                                   ) -> pd.DataFrame:
    """Reemplaza ``Defunciones_Anuales`` con la serie histórica oficial."""
    cliente = cliente or DatosSaludArClient()
    log.info("Capa 3 | Enriqueciendo con defunciones reales...")
    df_real = cliente.obtener_defunciones_por_provincia_anio()
    return _enriquecer_columna_anio_provincia(
        df_maestro, df_real,
        columna_destino="Defunciones_Anuales",
        columna_real="Defunciones",
        nombre_fuente="EstVitales",
    )


def enriquecer_con_nacimientos(df_maestro: pd.DataFrame,
                                    cliente: DatosSaludArClient | None = None,
                                    ) -> pd.DataFrame:
    """Reemplaza ``Nacimientos_Anuales`` con la serie histórica oficial."""
    cliente = cliente or DatosSaludArClient()
    log.info("Capa 3 | Enriqueciendo con nacimientos reales...")
    df_real = cliente.obtener_nacimientos_por_provincia_anio()
    return _enriquecer_columna_anio_provincia(
        df_maestro, df_real,
        columna_destino="Nacimientos_Anuales",
        columna_real="Nacimientos",
        nombre_fuente="EstVitales",
    )


def enriquecer_con_todas_las_fuentes(
    df_maestro: pd.DataFrame,
    cliente: DatosSaludArClient | None = None,
) -> pd.DataFrame:
    """Aplica todas las capas (REFES + Dengue + VIH + Médicos + Vitales).

    Es el orquestador completo: una sola llamada activa todas las fuentes
    reales del Min. Salud, manteniendo trazabilidad por columna.

    Args:
        df_maestro: Panel maestro sintético.
        cliente: Cliente compartido (evita re-instanciar).

    Returns:
        Panel enriquecido con columnas ``Fuente_*`` por cada variable.
    """
    cliente = cliente or DatosSaludArClient()
    log.info("=" * 60)
    log.info("Aplicando enriquecimiento completo (Capa 1 + 2 + 3)")
    log.info("=" * 60)
    df = df_maestro
    df = enriquecer_con_refes(df, cliente=cliente)        # Capa 1
    df = enriquecer_con_dengue(df, cliente=cliente)       # Capa 2
    df = enriquecer_con_vih(df, cliente=cliente)          # Capa 2
    df = enriquecer_con_medicos(df, cliente=cliente)      # Capa 3
    df = enriquecer_con_defunciones(df, cliente=cliente)  # Capa 3
    df = enriquecer_con_nacimientos(df, cliente=cliente)  # Capa 3
    return df


def reporte_cobertura_completo(df: pd.DataFrame) -> pd.DataFrame:
    """Construye un reporte de cobertura por columna y por fuente.

    Útil para la página de Streamlit y para anexar a la tesis.

    Args:
        df: Panel ya enriquecido (con columnas ``Fuente_*``).

    Returns:
        DataFrame con columnas ``[Variable, Fuente, Filas, Pct]``.
    """
    cols_fuente = [c for c in df.columns if c.startswith("Fuente_")]
    if not cols_fuente:
        return pd.DataFrame(columns=["Variable", "Fuente", "Filas", "Pct"])

    filas = []
    for col in cols_fuente:
        variable = col.replace("Fuente_", "")
        for fuente, count in df[col].value_counts().items():
            filas.append({
                "Variable": variable,
                "Fuente": fuente,
                "Filas": int(count),
                "Pct": round(count / len(df) * 100, 1),
            })
    return pd.DataFrame(filas).sort_values(
        ["Variable", "Fuente"]
    ).reset_index(drop=True)


def reporte_cobertura_refes(df: pd.DataFrame) -> pd.DataFrame:
    """Resume la cobertura REFES vs sintético por provincia.

    Útil para mostrar en la app y en la documentación de la tesis cuáles
    jurisdicciones quedaron con datos reales y cuáles dependen del sintético.

    Args:
        df: DataFrame ya enriquecido por ``enriquecer_con_refes``.

    Returns:
        DataFrame con conteos por provincia y % cobertura REFES.

    Ejemplo:
        >>> reporte = reporte_cobertura_refes(df_enriquecido)
        >>> reporte.head()
    """
    if "Fuente_Centros" not in df.columns:
        raise ValueError(
            "El DataFrame no fue enriquecido. Llamá a enriquecer_con_refes primero."
        )
    pivot = (
        df.assign(__es_refes=(df["Fuente_Centros"] == "REFES").astype(int))
        .groupby("Provincia")
        .agg(Filas_Total=("Año", "count"),
              Filas_REFES=("__es_refes", "sum"))
        .reset_index()
    )
    pivot["Pct_Cobertura_REFES"] = (
        pivot["Filas_REFES"] / pivot["Filas_Total"] * 100
    ).round(1)
    return pivot.sort_values("Pct_Cobertura_REFES", ascending=False)
