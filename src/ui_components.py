"""Componentes de UI reutilizables para la app Streamlit.

Centraliza helpers que se usan en varias páginas: tarjetas de KPI con
trazabilidad de fuente, badges de fiabilidad, tooltips, etc.

Diseñado para que cualquier página pueda mostrar un KPI con un solo
llamado, garantizando que el origen del dato siempre esté disponible
para el usuario (defensa académica del proyecto).
"""
from __future__ import annotations

from typing import Any

import streamlit as st

from src import config


def _formatear_url(url: str | None, texto: str | None = None) -> str:
    """Devuelve un link Markdown si la URL es válida, sino el texto plano."""
    if not url:
        return texto or "—"
    return f"[{texto or url}]({url})"


def _almacenamiento_para_nivel(nivel: str, fuente: dict) -> str:
    """Describe dónde reside físicamente el dato según su nivel.

    Permite responder al usuario "¿de dónde lo lee la app?" sin tener
    que documentar ese campo en cada entrada del catálogo.
    """
    # Override explícito si el catálogo lo declara
    if "almacenamiento" in fuente:
        return fuente["almacenamiento"]
    if nivel == "real":
        return ("Descargado en vivo desde la API oficial "
                "(`src/api_clients.py`) con caché local en `src/.api_cache/`.")
    if nivel in ("calibrado", "sintetico"):
        return ("Google Sheet (pestaña `Datos`), generado por "
                "`src/data_generator.py` y editable desde la página `Editor`.")
    if nivel == "modelo":
        return ("Calculado en runtime por el modelo ML entrenado en la "
                "sesión actual. No se almacena.")
    if nivel == "derivado":
        return ("Calculado en runtime a partir de los valores del catálogo. "
                "No se almacena.")
    if nivel == "estandar":
        return "Constante normativa definida en `src/config.py`."
    return "—"


def render_popover_fuente(fuente_key: str) -> None:
    """Renderiza el contenido de un popover con la trazabilidad del KPI.

    Pensado para usarse dentro de un ``with st.popover(...):`` o como
    bloque suelto. Lee el catálogo ``FUENTES_VARIABLES`` y muestra
    nivel de fiabilidad, descripción, origen, dataset oficial, link al
    portal, año de referencia y limitaciones conocidas.

    Args:
        fuente_key: Clave en ``config.FUENTES_VARIABLES``. Si no
            existe, muestra un mensaje de "no documentado".
    """
    fuente = config.FUENTES_VARIABLES.get(fuente_key)
    if fuente is None:
        st.warning(
            f"⚠️ La fuente del dato '{fuente_key}' no está documentada en "
            f"`config.FUENTES_VARIABLES`. Agregala para que aparezca acá."
        )
        return

    nivel = fuente.get("nivel", "sintetico")
    meta_nivel = config.NIVELES_FIABILIDAD.get(nivel, {})
    icono = meta_nivel.get("icono", "ℹ️")
    etiqueta = meta_nivel.get("etiqueta", nivel)
    color = meta_nivel.get("color", "#6B7280")

    st.markdown(
        f"""
        <div style="
            border-left: 4px solid {color};
            padding: .4rem .8rem;
            background: rgba(0,0,0,0.03);
            margin-bottom: .6rem;
        ">
        <b>{icono} Nivel de fiabilidad:</b> {etiqueta}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if "descripcion" in fuente:
        st.markdown(f"**Qué representa:** {fuente['descripcion']}")

    if "origen" in fuente:
        st.markdown(f"**Cómo se obtiene:** {fuente['origen']}")

    almacenamiento = _almacenamiento_para_nivel(nivel, fuente)
    if almacenamiento and almacenamiento != "—":
        st.markdown(f"**Dónde se almacena:** {almacenamiento}")

    if fuente.get("dataset"):
        link = _formatear_url(fuente.get("url_dataset"), fuente["dataset"])
        st.markdown(f"**Dataset oficial:** {link}")

    if fuente.get("url_referencia") and not fuente.get("dataset"):
        st.markdown(
            f"**Referencia metodológica:** "
            f"{_formatear_url(fuente['url_referencia'])}"
        )

    if fuente.get("anio_referencia"):
        st.markdown(f"**Año de referencia:** {fuente['anio_referencia']}")

    if fuente.get("cobertura"):
        st.markdown(f"**Cobertura del panel:** {fuente['cobertura']}")

    if fuente.get("depende_de"):
        deps = ", ".join(f"`{d}`" for d in fuente["depende_de"])
        st.markdown(f"**Depende de:** {deps}")

    if fuente.get("valor_constante") is not None:
        st.markdown(f"**Valor constante:** `{fuente['valor_constante']}`")

    if fuente.get("limitacion"):
        st.warning(f"⚠️ **Limitación:** {fuente['limitacion']}")


def _render_delta_html(delta: str | None, delta_color: str) -> str:
    """Construye el HTML del bloque delta con altura fija.

    El bloque delta SIEMPRE se rendea con la misma altura (1.5rem),
    sea o no haya valor. Cuando no hay delta, devolvemos un
    placeholder vacío con la misma altura para garantizar alineación
    pixel-perfect entre columnas.
    """
    altura = "1.5rem"
    if delta is None:
        return (
            f'<div style="height:{altura}; line-height:{altura};">'
            f'&nbsp;</div>'
        )
    delta_str = str(delta).strip()
    es_negativo = delta_str.startswith("-")
    es_cero = delta_str.lstrip("-").lstrip("+") in ("0", "0,00", "0.00", "0,0", "0.0")

    if delta_color == "off" or es_cero:
        color = "rgba(160,160,160,0.85)"
        flecha = ""
    else:
        invertir = (delta_color == "inverse")
        if es_negativo:
            color = "#16A34A" if invertir else "#DC2626"
            flecha = "↓"
        else:
            color = "#DC2626" if invertir else "#16A34A"
            flecha = "↑"
    return (
        f'<div style="height:{altura}; line-height:{altura}; '
        f'font-size:0.875rem; color:{color};">'
        f'{flecha} {delta_str}</div>'
    )


def kpi_con_fuente(
    label: str,
    value: str,
    fuente_key: str,
    delta: str | None = None,
    delta_color: str = "normal",
    help_text: str | None = None,
) -> None:
    """Renderiza un KPI con ícono de fiabilidad y popover de origen.

    Construye el KPI con HTML manual para garantizar alineación
    pixel-perfect entre columnas (el delta opcional siempre reserva su
    altura). Cualquier usuario puede abrir el popover "📖 Ver origen
    del dato" para inspeccionar la trazabilidad académica del KPI sin
    salir de la página.

    Args:
        label: Etiqueta del KPI (ej. "Tasa actual 2024").
        value: Valor formateado a mostrar (ej. "19,30 / 1000").
        fuente_key: Clave en ``config.FUENTES_VARIABLES``.
        delta: Variación opcional. Si es None, igual reserva el espacio.
        delta_color: 'normal' | 'inverse' | 'off'.
        help_text: Tooltip nativo del browser. Si no se pasa, usa la
            descripción de la fuente.
    """
    fuente = config.FUENTES_VARIABLES.get(fuente_key, {})
    nivel = fuente.get("nivel", "sintetico")
    icono = config.NIVELES_FIABILIDAD.get(nivel, {}).get("icono", "ℹ️")

    tooltip = (help_text or fuente.get("descripcion") or "").replace('"', "'")
    title_attr = f' title="{tooltip}"' if tooltip else ""

    delta_html = _render_delta_html(delta, delta_color)

    bloque_html = (
        f'<div>'
        f'  <div style="font-size:0.875rem; color:rgba(160,160,160,0.95); '
        f'height:1.4rem; line-height:1.4rem; margin-bottom:0.25rem;"{title_attr}>'
        f'{icono} {label}'
        f'  </div>'
        f'  <div style="font-size:1.875rem; font-weight:600; '
        f'line-height:2.2rem; height:2.2rem; margin-bottom:0.4rem;">'
        f'{value}'
        f'  </div>'
        f'  {delta_html}'
        f'</div>'
    )
    st.markdown(bloque_html, unsafe_allow_html=True)

    with st.popover("📖 Ver origen del dato", use_container_width=True):
        render_popover_fuente(fuente_key)


def popover_origen_chart(
    label: str,
    fuente_keys: list[str],
    icono: str = "📖",
) -> None:
    """Popover compacto que documenta el origen de un chart o mapa.

    Útil cuando un gráfico combina varias series/variables y queremos
    que el usuario pueda inspeccionar el origen de cada una en un solo
    botón al lado del título.

    Args:
        label: Texto del botón (ej. "Origen de los datos").
        fuente_keys: Lista de claves en ``config.FUENTES_VARIABLES`` a
            documentar dentro del popover.
        icono: Emoji al inicio del botón.

    Ejemplo:
        >>> popover_origen_chart(
        ...     "Origen de los datos",
        ...     ["Tasa_Nacional_Actual", "Tasa_Nacional_Proyectada"],
        ... )
    """
    with st.popover(f"{icono} {label}", use_container_width=True):
        for i, key in enumerate(fuente_keys):
            if i > 0:
                st.markdown("---")
            render_popover_fuente(key)


def leyenda_niveles() -> None:
    """Renderiza una leyenda compacta con los íconos y qué significan.

    Útil para mostrar una sola vez al inicio de la página, así el usuario
    sabe leer los íconos que verá en cada KPI.
    """
    items: list[str] = []
    for _clave, meta in config.NIVELES_FIABILIDAD.items():
        items.append(
            f"<span style='margin-right:1rem;'>"
            f"<b>{meta['icono']}</b> {meta['etiqueta']}"
            f"</span>"
        )
    st.markdown(
        f"<div style='font-size:.85rem; color:#6B7280; margin-bottom:.6rem;'>"
        f"{''.join(items)}</div>",
        unsafe_allow_html=True,
    )
