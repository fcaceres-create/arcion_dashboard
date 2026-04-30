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


def kpi_con_fuente(
    label: str,
    value: str,
    fuente_key: str,
    delta: str | None = None,
    delta_color: str = "normal",
    help_text: str | None = None,
) -> None:
    """Renderiza un ``st.metric`` con ícono de fiabilidad y popover de origen.

    Pensado para reemplazar llamadas directas a ``st.metric(...)`` cuando
    se quiere que el usuario pueda inspeccionar el origen del dato sin
    salir de la página.

    Args:
        label: Etiqueta del KPI (ej. "Tasa actual 2024").
        value: Valor formateado a mostrar (ej. "19,30 / 1000").
        fuente_key: Clave en ``config.FUENTES_VARIABLES`` con la
            trazabilidad del dato.
        delta: Variación opcional respecto a un baseline (igual que st.metric).
        delta_color: 'normal' | 'inverse' | 'off' (igual que st.metric).
        help_text: Tooltip adicional opcional. Si no se pasa, se usa la
            descripción de la fuente.

    Ejemplo:
        >>> kpi_con_fuente(
        ...     label="Tasa actual (2024)",
        ...     value="19,30 / 1000",
        ...     fuente_key="Tasa_Nacional_Actual",
        ... )
    """
    fuente = config.FUENTES_VARIABLES.get(fuente_key, {})
    nivel = fuente.get("nivel", "sintetico")
    icono = config.NIVELES_FIABILIDAD.get(nivel, {}).get("icono", "ℹ️")

    label_completo = f"{icono} {label}"
    tooltip = help_text or fuente.get("descripcion")

    st.metric(
        label_completo,
        value,
        delta=delta,
        delta_color=delta_color,
        help=tooltip,
    )

    with st.popover("📖 Ver origen del dato", use_container_width=True):
        render_popover_fuente(fuente_key)


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
