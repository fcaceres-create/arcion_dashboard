"""Clientes para APIs públicas: datos.gob.ar, World Bank y OPS.

Características:

- Caché local en archivos JSON (TTL configurable) para no golpear
  innecesariamente las APIs durante el desarrollo.
- Reintentos con backoff exponencial usando ``tenacity``.
- Manejo defensivo de errores: si la API falla, se devuelve ``None``
  y se loggea el problema (no se rompe el pipeline).

Ejemplo de uso:
    >>> from src.api_clients import DatosGobArClient, WorldBankClient
    >>> cli = WorldBankClient()
    >>> df = cli.obtener_indicador("SP.POP.TOTL")  # población total Argentina
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import requests
from tenacity import (
    retry, stop_after_attempt, wait_exponential, retry_if_exception_type,
)

from src import config
from src.utils import setup_logger

log = setup_logger(__name__)


# ---------------------------------------------------------------------
# Caché local en JSON
# ---------------------------------------------------------------------
class CachéAPI:
    """Caché simple en disco basado en hash de la URL.

    Args:
        directorio: Carpeta donde guardar los .json.
        ttl_horas: Tiempo de vida del caché. Por defecto 24h.

    Ejemplo:
        >>> cache = CachéAPI()
        >>> cache.guardar("https://api/.../x", {"foo": "bar"})
        >>> cache.leer("https://api/.../x")
        {'foo': 'bar'}
    """

    def __init__(self, directorio: Path | None = None, ttl_horas: int = 24):
        self.directorio = directorio or config.RUTA_API_CACHE
        self.directorio.mkdir(parents=True, exist_ok=True)
        self.ttl = timedelta(hours=ttl_horas)

    def _ruta_para(self, url: str) -> Path:
        h = hashlib.md5(url.encode("utf-8")).hexdigest()
        return self.directorio / f"{h}.json"

    def leer(self, url: str) -> Any | None:
        """Lee del caché si existe y no está vencido. Si no, devuelve None."""
        archivo = self._ruta_para(url)
        if not archivo.exists():
            return None
        edad = datetime.now() - datetime.fromtimestamp(archivo.stat().st_mtime)
        if edad > self.ttl:
            log.debug("Caché vencido para %s", url)
            return None
        try:
            with open(archivo, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Caché corrupto en %s: %s", archivo, exc)
            return None

    def guardar(self, url: str, datos: Any) -> None:
        """Persiste el payload en disco."""
        archivo = self._ruta_para(url)
        try:
            with open(archivo, "w", encoding="utf-8") as f:
                json.dump(datos, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            log.warning("No se pudo escribir caché %s: %s", archivo, exc)


# ---------------------------------------------------------------------
# Helper de request con retry
# ---------------------------------------------------------------------
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((requests.RequestException,)),
    reraise=True,
)
def _hacer_request(url: str, params: dict | None = None) -> dict | list:
    """Realiza un GET con retry exponencial.

    Args:
        url: URL completa (sin params).
        params: Diccionario de query params.

    Returns:
        Cuerpo JSON parseado.

    Raises:
        requests.RequestException: si todos los reintentos fallan.
    """
    log.debug("GET %s | params=%s", url, params)
    resp = requests.get(url, params=params, timeout=config.TIMEOUT_API)
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------
# datos.gob.ar (Series de Tiempo)
# ---------------------------------------------------------------------
class DatosGobArClient:
    """Cliente para la API pública de Series de Tiempo de Argentina.

    Documentación oficial:
        https://datosgobar.github.io/series-tiempo-ar-api/

    Ejemplo:
        >>> cli = DatosGobArClient()
        >>> df = cli.obtener_serie("103.1_I2N_2016_M_19")  # IPC mensual
        >>> df.head()
    """

    URL_BASE = config.URL_DATOS_GOB

    def __init__(self):
        self.cache = CachéAPI()

    def obtener_serie(self, id_serie: str,
                       formato: str = "json",
                       limit: int = 5000) -> pd.DataFrame | None:
        """Descarga una serie por su ID oficial.

        Args:
            id_serie: ID de la serie (ej. ``"143.3_NO_PR_2004_A_21"``).
            formato: 'json' o 'csv'. Recomendado 'json' para parseo.
            limit: Cantidad máxima de filas.

        Returns:
            DataFrame con columnas ``[fecha, valor]`` o None si falla.
        """
        params = {"ids": id_serie, "format": formato, "limit": limit}
        url_completa = f"{self.URL_BASE}?ids={id_serie}&format={formato}&limit={limit}"

        # Caché
        cached = self.cache.leer(url_completa)
        if cached is not None:
            log.info("Serie %s recuperada de caché", id_serie)
            return self._parsear_respuesta(cached, id_serie)

        try:
            payload = _hacer_request(self.URL_BASE, params=params)
        except requests.RequestException as exc:
            log.error("Falló datos.gob.ar para %s: %s", id_serie, exc)
            return None

        self.cache.guardar(url_completa, payload)
        return self._parsear_respuesta(payload, id_serie)

    @staticmethod
    def _parsear_respuesta(payload: dict, id_serie: str) -> pd.DataFrame | None:
        """Convierte el payload JSON en DataFrame."""
        if not payload or "data" not in payload:
            log.warning("Respuesta sin datos para %s", id_serie)
            return None
        registros = payload["data"]
        df = pd.DataFrame(registros, columns=["fecha", "valor"])
        df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
        df["valor"] = pd.to_numeric(df["valor"], errors="coerce")
        df["id_serie"] = id_serie
        return df


# ---------------------------------------------------------------------
# World Bank
# ---------------------------------------------------------------------
class WorldBankClient:
    """Cliente para la API del Banco Mundial (indicadores macro/salud).

    Documentación:
        https://datahelpdesk.worldbank.org/knowledgebase/articles/889392

    Ejemplo:
        >>> cli = WorldBankClient()
        >>> df = cli.obtener_indicador("SP.POP.TOTL", anio_inicio=2015)
        >>> df.head()
    """

    URL_BASE = config.URL_WORLD_BANK

    def __init__(self):
        self.cache = CachéAPI()

    def obtener_indicador(self, indicador: str,
                            anio_inicio: int = config.ANIO_INICIO_HISTORICO,
                            anio_fin: int = config.ANIO_FIN_HISTORICO,
                            ) -> pd.DataFrame | None:
        """Descarga un indicador para Argentina.

        Args:
            indicador: Código del indicador (ej. ``"SP.POP.TOTL"`` población).
            anio_inicio: Año inicial.
            anio_fin: Año final.

        Returns:
            DataFrame con columnas ``[anio, valor, indicador]`` o None.
        """
        url = f"{self.URL_BASE}{indicador}"
        params = {
            "format": "json",
            "date": f"{anio_inicio}:{anio_fin}",
            "per_page": 200,
        }
        url_completa = f"{url}?date={anio_inicio}:{anio_fin}&format=json"

        cached = self.cache.leer(url_completa)
        if cached is not None:
            log.info("Indicador %s recuperado de caché", indicador)
            return self._parsear_respuesta(cached, indicador)

        try:
            payload = _hacer_request(url, params=params)
        except requests.RequestException as exc:
            log.error("Falló World Bank para %s: %s", indicador, exc)
            return None

        self.cache.guardar(url_completa, payload)
        return self._parsear_respuesta(payload, indicador)

    @staticmethod
    def _parsear_respuesta(payload: list, indicador: str) -> pd.DataFrame | None:
        """La API del Banco Mundial devuelve [metadata, datos]."""
        if not isinstance(payload, list) or len(payload) < 2:
            log.warning("Respuesta inesperada para %s", indicador)
            return None
        registros = payload[1] or []
        if not registros:
            return pd.DataFrame(columns=["anio", "valor", "indicador"])
        df = pd.DataFrame([
            {"anio": int(r["date"]),
              "valor": r["value"],
              "indicador": indicador}
            for r in registros
        ]).sort_values("anio").reset_index(drop=True)
        return df


# ---------------------------------------------------------------------
# datos.salud.gob.ar (CKAN — Ministerio de Salud)
# ---------------------------------------------------------------------
class DatosSaludArClient:
    """Cliente para el portal CKAN del Ministerio de Salud de la Nación.

    Permite descargar datasets oficiales como REFES (Registro Federal de
    Establecimientos de Salud), filtrar por servicios específicos
    (bancos de sangre, hemoterapia) y entregar agregaciones por provincia.

    Notas:
        - El portal expone su API CKAN en ``/api/3/action/...``.
        - Por una cadena de certificados incompleta del CDN del Ministerio
          (ver ``config.VERIFICAR_SSL_DATOS_SALUD``), se desactiva la
          verificación SSL. Esto es seguro porque los datos son públicos
          y no enviamos credenciales.

    Ejemplo:
        >>> cli = DatosSaludArClient()
        >>> df = cli.obtener_centros_hemoterapia_por_provincia(anio=2025)
        >>> df.head()
    """

    URL_BASE: str = config.URL_DATOS_SALUD
    DATASET_REFES: str = config.DATASET_REFES_ID

    # Términos para identificar centros de hemoterapia en REFES
    PATRON_INCLUIR_NOMBRE: str = (
        r"hemoterapia|hemocentro|banco.*sangre|"
        r"servicio.*transfusional|centro.*transfusional"
    )
    PATRON_EXCLUIR_NOMBRE: str = r"hemodialisis|hemodi[áa]li|hemodinamia"
    TIPOLOGIA_BANCO_SANGRE: str = "Bancos de Sangre"

    def __init__(self):
        self.cache = CachéAPI()
        # Sesión configurada una sola vez (reusa conexión TCP).
        self.session = requests.Session()
        if not config.VERIFICAR_SSL_DATOS_SALUD:
            urllib3 = requests.packages.urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    # -------- API pública --------
    def listar_recursos_refes(self) -> list[dict] | None:
        """Devuelve metadatos de todos los snapshots REFES (lista de dicts).

        Cada dict incluye: ``name``, ``url``, ``format``, ``last_modified``,
        ``size``, ``anio_inferido`` (parseado del nombre del recurso).
        """
        payload = self._package_show(self.DATASET_REFES)
        if not payload:
            return None
        recursos = payload.get("resources", [])
        # Anotamos año inferido del nombre
        for r in recursos:
            r["anio_inferido"] = self._inferir_anio(r.get("name", ""))
        return recursos

    def descargar_snapshot_refes(self, anio: int,
                                    forzar_recarga: bool = False
                                    ) -> pd.DataFrame | None:
        """Descarga el snapshot REFES más cercano al año pedido.

        Si no existe snapshot exacto, devuelve el más reciente anterior.
        Soporta CSV y XLSX (prefiere CSV si ambos existen).

        Args:
            anio: Año objetivo del snapshot.
            forzar_recarga: Si True, ignora el caché local.

        Returns:
            DataFrame con todos los establecimientos del snapshot.

        Ejemplo:
            >>> df = cli.descargar_snapshot_refes(2024)
            >>> df["provincia_nombre"].nunique()
            24
        """
        recursos = self.listar_recursos_refes()
        if not recursos:
            return None

        recurso = self._elegir_recurso_para_anio(recursos, anio)
        if not recurso:
            log.warning("No se encontró snapshot REFES adecuado para %d", anio)
            return None

        log.info("REFES %d -> snapshot '%s' (formato %s)",
                 anio, recurso["name"], recurso["format"])
        return self._descargar_recurso(recurso, forzar_recarga=forzar_recarga)

    def filtrar_centros_hemoterapia(self, df_refes: pd.DataFrame) -> pd.DataFrame:
        """Filtra el DataFrame REFES dejando solo centros de hemoterapia.

        Combina la tipología oficial 'Bancos de Sangre' con coincidencias
        en el nombre del establecimiento (hemoterapia, hemocentro, banco
        de sangre), excluyendo falsos positivos (hemodiálisis, hemodinamia).

        Es robusto a las variaciones de esquema entre snapshots:
            - 2025+: columna ``tipologia_nombre``.
            - 2019, 2021: columna ``tipologia``.
            - 2018: solo ``tipologia_sigla`` — fallback únicamente a nombre.

        Args:
            df_refes: DataFrame crudo de REFES (con columnas normalizadas
                a lowercase por ``_descargar_recurso``).

        Returns:
            Subset de filas que califican como centros de hemoterapia.

        Ejemplo:
            >>> df_refes = cli.descargar_snapshot_refes(2025)
            >>> centros = cli.filtrar_centros_hemoterapia(df_refes)
            >>> len(centros)  # ~50-200 según snapshot
        """
        cols = set(df_refes.columns)
        if "establecimiento_nombre" not in cols:
            log.error("Snapshot sin 'establecimiento_nombre'. Cols: %s", sorted(cols))
            return df_refes.iloc[0:0].copy()

        nombre = df_refes["establecimiento_nombre"].fillna("").astype(str)

        # Detectamos la columna de tipología textual (varía entre años)
        col_tipologia = next(
            (c for c in ("tipologia_nombre", "tipologia") if c in cols),
            None,
        )
        if col_tipologia:
            tipologia = df_refes[col_tipologia].fillna("").astype(str).str.strip()
            match_tipologia = tipologia == self.TIPOLOGIA_BANCO_SANGRE
        else:
            log.warning(
                "Snapshot sin tipología textual; uso solo match por nombre."
            )
            match_tipologia = pd.Series(False, index=df_refes.index)

        match_nombre = nombre.str.contains(
            self.PATRON_INCLUIR_NOMBRE, case=False, regex=True, na=False
        )
        excluir = nombre.str.contains(
            self.PATRON_EXCLUIR_NOMBRE, case=False, regex=True, na=False
        )

        mask = (match_tipologia | match_nombre) & ~excluir
        return df_refes.loc[mask].copy()

    def obtener_centros_hemoterapia_por_provincia(
        self, anio: int = 2025,
    ) -> pd.DataFrame | None:
        """Atajo: descarga + filtra + agrega por provincia para un año.

        Args:
            anio: Año del snapshot a usar.

        Returns:
            DataFrame con columnas ``[Provincia, Año, Centros_Hemoterapia]``
            usando los nombres canónicos del proyecto (mayúscula y acentos).

        Ejemplo:
            >>> df = cli.obtener_centros_hemoterapia_por_provincia(2024)
            >>> df.head()
                  Provincia   Año  Centros_Hemoterapia
            0  Buenos Aires  2024                   42
            1          CABA  2024                   18
        """
        df_refes = self.descargar_snapshot_refes(anio)
        if df_refes is None:
            return None
        centros = self.filtrar_centros_hemoterapia(df_refes)

        # Agregamos por provincia usando nombre normalizado, luego mapeamos
        # de vuelta a la grafía canónica del proyecto.
        from src.utils import normalizar_provincia
        from src import config as cfg

        centros["__prov_norm"] = centros["provincia_nombre"].apply(normalizar_provincia)

        mapa_canonico = {
            normalizar_provincia(p): p for p in cfg.PROVINCIAS_ARGENTINA.keys()
        }

        agregado = (
            centros.groupby("__prov_norm")
            .size()
            .rename("Centros_Hemoterapia")
            .reset_index()
        )
        agregado["Provincia"] = agregado["__prov_norm"].map(mapa_canonico)
        agregado["Año"] = anio
        agregado = agregado.dropna(subset=["Provincia"]).copy()
        return agregado[["Provincia", "Año", "Centros_Hemoterapia"]].sort_values(
            "Provincia"
        ).reset_index(drop=True)

    # =================================================================
    # CAPA 2 — Vigilancia epidemiológica
    # =================================================================
    def obtener_casos_vih_por_provincia_anio(self) -> pd.DataFrame | None:
        """Devuelve el panel oficial de casos de VIH por provincia × año.

        Fuente: ``notificacion-de-casos-de-vih`` (Min. Salud).
        Cobertura típica: 2014–2023 según último CSV publicado.

        El dataset usa **códigos INDEC numéricos** en la columna
        ``jurisdiccion`` (200 = Argentina total, 6 = Buenos Aires, 2 = CABA...).
        Mapeamos vía ``config.CODIGO_INDEC_A_PROVINCIA``.

        Returns:
            DataFrame con columnas ``[Provincia, Año, Casos_VIH]``.
        """
        recurso = self._buscar_recurso(
            config.DATASET_VIH_ID,
            criterio=lambda r: ("jurisdic" in r.get("name", "").lower()
                                 and r.get("format") == "CSV"),
            preferir_mas_reciente=True,
        )
        if not recurso:
            log.error("No se encontró recurso VIH por jurisdicción")
            return None

        df = self._descargar_recurso(recurso, nombre_cache="vih_jurisdicciones")
        if df is None:
            return None

        df = df[df["sexo"].astype(str).str.lower().str.contains("ambos", na=False)]
        df = df.copy()
        df["codigo_indec"] = pd.to_numeric(
            df["jurisdiccion"], errors="coerce"
        ).astype("Int64")
        df["Provincia"] = df["codigo_indec"].map(config.CODIGO_INDEC_A_PROVINCIA)
        df = df.dropna(subset=["Provincia"]).copy()  # excluye 200 = ARG total

        df["Año"] = pd.to_numeric(df["anio"], errors="coerce").astype("Int64")
        df["Casos_VIH"] = pd.to_numeric(df["casos_vih"], errors="coerce").fillna(0).astype(int)
        df = df.dropna(subset=["Año"])
        df["Año"] = df["Año"].astype(int)

        return df[["Provincia", "Año", "Casos_VIH"]].sort_values(
            ["Provincia", "Año"]
        ).reset_index(drop=True)

    def obtener_casos_dengue_por_provincia_anio(self) -> pd.DataFrame | None:
        """Devuelve casos de dengue por provincia × año.

        Combina los CSVs anuales del dataset ``vigilancia-de-dengue-y-zika``,
        agregando por (Provincia, Año) y filtrando ``evento_nombre='Dengue'``.

        Returns:
            DataFrame con columnas ``[Provincia, Año, Casos_Dengue]``.
        """
        from src.utils import normalizar_provincia

        payload = self._package_show(config.DATASET_DENGUE_ID)
        if not payload:
            return None

        recursos = [r for r in payload.get("resources", [])
                    if r.get("format") in ("CSV", "XLSX", "XLS")]
        # Anotamos año del nombre del recurso
        for r in recursos:
            r["anio_inferido"] = self._inferir_anio(r.get("name", ""))

        paneles: list[pd.DataFrame] = []
        for r in recursos:
            anio = r.get("anio_inferido")
            if not anio:
                continue
            r_copy = dict(r)
            df = self._descargar_recurso(
                r_copy, nombre_cache=f"dengue_{anio}"
            )
            if df is None:
                continue
            # Buscamos columna de provincia, casos, año (varían entre snapshots).
            # Schema viejo (2018-2022): provincia_nombre, ano|año, cantidad_casos
            # Schema nuevo (2024+):    provincia_residencia, anio_min, cantidad
            col_prov = next(
                (c for c in ("provincia_nombre", "provincia_residencia",
                              "provincia")
                  if c in df.columns), None)
            col_id_prov = next(
                (c for c in ("provincia_id", "id_prov_indec_residencia")
                  if c in df.columns), None)
            col_casos = next(
                (c for c in ("cantidad_casos", "cantidad", "casos",
                              "casos_totales")
                  if c in df.columns), None)
            col_anio = next(
                (c for c in ("ano", "anio", "año", "anio_min")
                  if c in df.columns), None)
            col_evento = next(
                (c for c in ("evento_nombre", "evento") if c in df.columns),
                None,
            )
            if not (col_casos and col_anio and (col_prov or col_id_prov)):
                log.warning("Snapshot dengue %d sin columnas esperadas; skip",
                            anio)
                continue
            df = df.copy()
            if col_evento:
                df = df[df[col_evento].astype(str).str.lower().str.contains(
                    "dengue", na=False)]
            # Preferimos código INDEC numérico si está (mapeo más robusto)
            if col_id_prov:
                df["Provincia_raw"] = df[col_id_prov]
                df["__usa_id_indec"] = True
            else:
                df["Provincia_raw"] = df[col_prov]
                df["__usa_id_indec"] = False
            df = df[["Provincia_raw", col_anio, col_casos,
                      "__usa_id_indec"]].rename(columns={
                col_anio: "Año", col_casos: "Casos_Dengue",
            })
            paneles.append(df)

        if not paneles:
            return None

        df_all = pd.concat(paneles, ignore_index=True)
        df_all["Año"] = pd.to_numeric(df_all["Año"], errors="coerce").astype(
            "Int64"
        )
        df_all = df_all.dropna(subset=["Año"])
        df_all["Casos_Dengue"] = pd.to_numeric(
            df_all["Casos_Dengue"], errors="coerce"
        ).fillna(0)

        # Mapeo en dos vías: si la fila vino con código INDEC, mapeamos vía
        # CODIGO_INDEC_A_PROVINCIA; si vino con nombre, usamos normalización.
        mapa_nombre = {normalizar_provincia(p): p
                        for p in config.PROVINCIAS_ARGENTINA.keys()}

        def _mapear(row):
            if row["__usa_id_indec"]:
                try:
                    cod = int(row["Provincia_raw"])
                    return config.CODIGO_INDEC_A_PROVINCIA.get(cod)
                except (TypeError, ValueError):
                    return None
            return mapa_nombre.get(normalizar_provincia(str(row["Provincia_raw"])))

        df_all["Provincia"] = df_all.apply(_mapear, axis=1)
        df_all = df_all.dropna(subset=["Provincia"])

        agregado = (
            df_all.groupby(["Provincia", "Año"], as_index=False)["Casos_Dengue"]
            .sum()
        )
        agregado["Año"] = agregado["Año"].astype(int)
        agregado["Casos_Dengue"] = agregado["Casos_Dengue"].round().astype(int)
        return agregado.sort_values(["Provincia", "Año"]).reset_index(drop=True)

    # =================================================================
    # CAPA 3 — Recursos humanos y estadísticas vitales
    # =================================================================
    def obtener_medicos_por_provincia(self) -> pd.DataFrame | None:
        """Devuelve la cantidad de médicos por provincia (snapshot único).

        El dataset oficial ``profesionales-medicos-por-jurisdiccion`` está
        marcado como **DISCONTINUADO** y solo expone un snapshot histórico
        (no varía con el año). Lo replicamos para todos los años del rango
        histórico como variable cuasi-fija.

        Returns:
            DataFrame con columnas ``[Provincia, Medicos]``.
        """
        from src.utils import normalizar_provincia

        recurso = self._buscar_recurso(
            config.DATASET_MEDICOS_ID,
            criterio=lambda r: r.get("format") == "CSV",
        )
        if not recurso:
            return None

        df = self._descargar_recurso(recurso, nombre_cache="medicos")
        if df is None:
            return None

        col_prov = next(
            (c for c in ("provincia_desc", "provincia_nombre", "provincia")
              if c in df.columns), None)
        col_med = next(
            (c for c in ("medicos_cantidad_total", "medicos", "cantidad")
              if c in df.columns), None)
        if not (col_prov and col_med):
            log.error("Médicos: columnas no detectadas. Cols: %s",
                      list(df.columns))
            return None

        df = df[[col_prov, col_med]].rename(columns={
            col_prov: "Provincia_raw", col_med: "Medicos",
        })
        df["__prov_norm"] = df["Provincia_raw"].apply(normalizar_provincia)
        mapa = {normalizar_provincia(p): p
                for p in config.PROVINCIAS_ARGENTINA.keys()}
        df["Provincia"] = df["__prov_norm"].map(mapa)
        df = df.dropna(subset=["Provincia"]).copy()
        df["Medicos"] = pd.to_numeric(df["Medicos"], errors="coerce").astype(
            "Int64"
        )
        return df[["Provincia", "Medicos"]].sort_values("Provincia").reset_index(
            drop=True
        )

    def obtener_defunciones_por_provincia_anio(self) -> pd.DataFrame | None:
        """Devuelve panel de defunciones por provincia × año (1914-2024).

        Fuente: ``serie-historica-de-defunciones...``. El XLSX viene en
        formato wide (columnas = provincias) — lo desnormalizamos a long.
        """
        return self._descargar_serie_vital(
            dataset_id=config.DATASET_DEFUNCIONES_ID,
            nombre_variable="Defunciones",
            nombre_cache="defunciones",
        )

    def obtener_nacimientos_por_provincia_anio(self) -> pd.DataFrame | None:
        """Devuelve panel de nacimientos por provincia × año (1914-2024).

        Fuente: ``serie-historica-de-nacimientos...``. Mismo formato wide
        que defunciones, con typos de columnas (``medoza``, ``santiengo_...``)
        que normalizamos.
        """
        return self._descargar_serie_vital(
            dataset_id=config.DATASET_NACIMIENTOS_ID,
            nombre_variable="Nacimientos",
            nombre_cache="nacimientos",
        )

    # -------- Internas --------
    def _buscar_recurso(self, dataset_id: str,
                          criterio,
                          preferir_mas_reciente: bool = True) -> dict | None:
        """Busca el primer recurso de un dataset que cumple el criterio."""
        payload = self._package_show(dataset_id)
        if not payload:
            return None
        candidatos = [r for r in payload.get("resources", []) if criterio(r)]
        if not candidatos:
            return None
        if preferir_mas_reciente:
            candidatos.sort(key=lambda r: r.get("last_modified", ""), reverse=True)
        recurso = candidatos[0]
        recurso["anio_inferido"] = self._inferir_anio(recurso.get("name", "")) or 0
        return recurso

    def _descargar_serie_vital(self, dataset_id: str,
                                  nombre_variable: str,
                                  nombre_cache: str) -> pd.DataFrame | None:
        """Genérico para defunciones y nacimientos (mismo formato wide).

        Convierte el formato wide (anio + columnas por provincia) a long
        (Provincia, Año, valor).
        """
        from src.utils import normalizar_provincia

        recurso = self._buscar_recurso(
            dataset_id,
            criterio=lambda r: r.get("format") == "XLSX",
            preferir_mas_reciente=True,
        )
        if not recurso:
            return None

        df = self._descargar_recurso(recurso, nombre_cache=nombre_cache)
        if df is None:
            return None

        # Detectamos columna de año
        col_anio = next(
            (c for c in ("anio", "año", "ano", "year") if c in df.columns), None)
        if not col_anio:
            log.error("%s: columna de año no encontrada. Cols: %s",
                      nombre_variable, list(df.columns))
            return None

        # Las columnas de provincias son todas las que no son año ni "total"
        # ni "república argentina" / "total_argentina"
        cols_provincia = [
            c for c in df.columns
            if c != col_anio
            and "total" not in c.lower()
            and "argentina" not in c.lower()
        ]

        df_long = df[[col_anio] + cols_provincia].melt(
            id_vars=[col_anio],
            var_name="Provincia_raw",
            value_name=nombre_variable,
        )
        df_long["Año"] = pd.to_datetime(
            df_long[col_anio], errors="coerce"
        ).dt.year
        # Si era ya un int, fallback
        df_long["Año"] = df_long["Año"].fillna(
            pd.to_numeric(df_long[col_anio], errors="coerce")
        ).astype("Int64")
        df_long = df_long.dropna(subset=["Año"])

        df_long["__prov_norm"] = df_long["Provincia_raw"].apply(
            lambda x: normalizar_provincia(str(x).replace("_", " "))
        )
        # Mapeo de los typos del dataset oficial
        typos = {
            "medoza": "mendoza",
            "santiengo del estero": "santiago del estero",
            "tierra del fuego-antartida-islas-atlantico sud": "tierra del fuego",
            "tierra del fuego antartida islas atlantico sud": "tierra del fuego",
            "capital federal": "caba",
        }
        df_long["__prov_norm"] = df_long["__prov_norm"].replace(typos)

        mapa = {normalizar_provincia(p): p
                for p in config.PROVINCIAS_ARGENTINA.keys()}
        df_long["Provincia"] = df_long["__prov_norm"].map(mapa)
        df_long = df_long.dropna(subset=["Provincia", nombre_variable]).copy()
        df_long["Año"] = df_long["Año"].astype(int)
        df_long[nombre_variable] = df_long[nombre_variable].astype(int)

        return df_long[["Provincia", "Año", nombre_variable]].sort_values(
            ["Provincia", "Año"]
        ).reset_index(drop=True)

    def _package_show(self, dataset_id: str) -> dict | None:
        """Llama a CKAN /api/3/action/package_show con caché."""
        url = f"{self.URL_BASE}/api/3/action/package_show"
        cache_key = f"{url}?id={dataset_id}"
        cached = self.cache.leer(cache_key)
        if cached is not None:
            return cached.get("result") if "result" in cached else None
        try:
            resp = self.session.get(
                url, params={"id": dataset_id},
                timeout=config.TIMEOUT_API,
                verify=config.VERIFICAR_SSL_DATOS_SALUD,
            )
            resp.raise_for_status()
            payload = resp.json()
        except (requests.RequestException, ValueError) as exc:
            log.error("Falló package_show(%s): %s", dataset_id, exc)
            return None
        self.cache.guardar(cache_key, payload)
        return payload.get("result")

    def _inferir_anio(self, nombre_recurso: str) -> int | None:
        """Intenta extraer el año del nombre del recurso (regex)."""
        import re
        m = re.search(r"(20\d{2})", nombre_recurso or "")
        return int(m.group(1)) if m else None

    def _elegir_recurso_para_anio(self, recursos: list[dict],
                                     anio: int) -> dict | None:
        """Selecciona el snapshot más apropiado para un año dado.

        Prefiere snapshot del mismo año en CSV; si no existe, el más
        reciente anterior; si tampoco hay, el más reciente posterior.
        """
        # Solo formatos parseables
        candidatos = [r for r in recursos
                       if r.get("format") in ("CSV", "XLSX", "XLS")
                       and r.get("anio_inferido")]
        if not candidatos:
            return None

        # Match exacto (preferimos CSV si hay varios)
        exactos = [r for r in candidatos if r["anio_inferido"] == anio]
        if exactos:
            csvs = [r for r in exactos if r["format"] == "CSV"]
            return csvs[0] if csvs else exactos[0]

        # Si no, el más reciente anterior
        anteriores = sorted(
            [r for r in candidatos if r["anio_inferido"] <= anio],
            key=lambda r: r["anio_inferido"], reverse=True,
        )
        if anteriores:
            return anteriores[0]

        # En último caso, el más antiguo posterior
        posteriores = sorted(
            [r for r in candidatos if r["anio_inferido"] > anio],
            key=lambda r: r["anio_inferido"],
        )
        return posteriores[0] if posteriores else None

    def _descargar_recurso(self, recurso: dict,
                              forzar_recarga: bool = False,
                              nombre_cache: str | None = None,
                              ) -> pd.DataFrame | None:
        """Descarga un recurso CKAN y lo parsea a DataFrame con caché.

        Args:
            recurso: dict de CKAN con al menos ``url``, ``format``,
                opcionalmente ``anio_inferido``.
            forzar_recarga: si True ignora el caché.
            nombre_cache: clave del archivo de caché (sin extensión).
                Si es ``None``, se usa ``refes_<anio>`` (compatibilidad).
        """
        import io
        url = recurso["url"]
        formato = recurso.get("format", "").upper()

        # Caché en pickle (sin dependencias extra; archivo local de confianza)
        if nombre_cache is None:
            nombre_cache = f"refes_{recurso.get('anio_inferido', 0)}"
        archivo_cache = config.RUTA_API_CACHE / f"{nombre_cache}.pkl"
        if archivo_cache.exists() and not forzar_recarga:
            log.info("Snapshot %s recuperado de caché local", recurso["anio_inferido"])
            try:
                df_cache = pd.read_pickle(archivo_cache)
                return self._normalizar_columnas(df_cache)
            except Exception as exc:
                log.warning("Caché pickle corrupto, re-descargo: %s", exc)

        try:
            resp = self.session.get(
                url,
                timeout=config.TIMEOUT_DESCARGA_GRANDE,
                verify=config.VERIFICAR_SSL_DATOS_SALUD,
            )
            resp.raise_for_status()
        except requests.RequestException as exc:
            log.error("Falló descarga %s: %s", url, exc)
            return None

        df = self._parsear_payload(resp.content, formato, url)
        if df is None:
            return None
        df = self._normalizar_columnas(df)

        # Persistimos en pickle (mucho más rápido en futuras lecturas)
        try:
            df.to_pickle(archivo_cache)
        except Exception as exc:
            log.warning("No se pudo cachear como pickle: %s", exc)

        return df

    @staticmethod
    def _normalizar_columnas(df: pd.DataFrame) -> pd.DataFrame:
        """Normaliza headers a lowercase, sin BOM ni comillas ni espacios.

        El esquema REFES varía entre snapshots: 2018 usa minúsculas con BOM
        UTF-8, 2024 usa MAYÚSCULAS, 2025 usa minúsculas limpias. Esta
        función deja todo consistente.
        """
        df = df.copy()
        df.columns = [
            str(c).lower().strip().lstrip("﻿").strip('"').strip()
            for c in df.columns
        ]
        return df

    @staticmethod
    def _parsear_payload(contenido: bytes, formato: str,
                            url: str) -> pd.DataFrame | None:
        """Intenta parsear el payload con fallbacks de encoding/separator.

        Args:
            contenido: bytes crudos descargados.
            formato: 'CSV', 'XLSX' o 'XLS'.
            url: URL original (solo para logging).
        """
        import io
        if formato == "CSV":
            for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
                try:
                    return pd.read_csv(
                        io.BytesIO(contenido),
                        encoding=encoding, sep=None, engine="python",
                    )
                except UnicodeDecodeError:
                    continue
                except Exception as exc:
                    log.error("Error parseando CSV (%s) %s: %s",
                              encoding, url, exc)
                    return None
            log.error("Ningún encoding funcionó para %s", url)
            return None
        elif formato in ("XLSX", "XLS"):
            try:
                # Filtramos warning cosmético de openpyxl sobre estilos default
                import warnings
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    return pd.read_excel(io.BytesIO(contenido))
            except Exception as exc:
                log.error("Error parseando Excel %s: %s", url, exc)
                return None
        else:
            log.error("Formato %s no soportado", formato)
            return None


# ---------------------------------------------------------------------
# OPS / PAHO (placeholder)
# ---------------------------------------------------------------------
class OPSClient:
    """Placeholder para integración futura con OPS/PAHO.

    Actualmente la OPS no expone una API REST pública para los
    indicadores de hemoterapia. La descarga se realiza manualmente
    desde sus reportes en PDF (``Suministro de sangre para
    transfusiones en LATAM``).

    TODO: Cuando OPS publique una API, implementar aquí los métodos:
        - obtener_indicador_hemoterapia(pais, anio)
        - obtener_serie_donaciones(pais, anio_inicio, anio_fin)
    """

    URL_REPORTE_2023 = (
        "https://www.paho.org/es/documentos/"
        "suministro-sangre-para-transfusiones-2023"
    )

    def __init__(self):
        log.info("OPSClient en modo placeholder. Ver TODO en src/api_clients.py")

    def descargar_reporte(self, ruta_destino: Path) -> Path | None:
        """Descarga manual del PDF anual de OPS.

        Args:
            ruta_destino: Path donde guardar el PDF.

        Returns:
            Ruta del archivo descargado, o None si falla.
        """
        log.warning("Descarga manual desde %s", self.URL_REPORTE_2023)
        try:
            resp = requests.get(self.URL_REPORTE_2023, timeout=60)
            resp.raise_for_status()
            ruta_destino.write_bytes(resp.content)
            return ruta_destino
        except requests.RequestException as exc:
            log.error("Falló descarga OPS: %s", exc)
            return None
