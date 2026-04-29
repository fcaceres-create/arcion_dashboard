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

    # -------- Internas --------
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
                              forzar_recarga: bool = False) -> pd.DataFrame | None:
        """Descarga un recurso CKAN y lo parsea a DataFrame con caché."""
        import io
        url = recurso["url"]
        formato = recurso.get("format", "").upper()

        # Caché en pickle (sin dependencias extra; archivo local de confianza)
        archivo_cache = config.RUTA_API_CACHE / f"refes_{recurso['anio_inferido']}.pkl"
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
