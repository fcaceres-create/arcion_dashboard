"""Página: Editor de datos con autenticación.

Permite al administrador editar las hojas del Google Sheet de respaldo
directamente desde el navegador. Cualquier cambio guardado queda
persistente en la nube (no requiere acceso al equipo local).

Flujo:
    1. Usuario ingresa password en sidebar.
    2. Si coincide con ``st.secrets['admin']['password']`` desbloquea editor.
    3. Cada pestaña del Sheet aparece como tab editable.
    4. Botón "💾 Guardar cambios" sube las modificaciones al Sheet.
    5. Botón "🤖 Re-entrenar modelo" corre el pipeline en memoria.

⚠️ La app pública sigue siendo read-only para usuarios sin password.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st

RUTA_RAIZ = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RUTA_RAIZ))

st.set_page_config(page_title="ARCION · Editor", page_icon="🔐", layout="wide")
st.title("🔐 ARCION · Editor de datos")

# ---------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------
def _password_correcto() -> bool:
    """Devuelve True si el usuario está autenticado."""
    if "admin_logged_in" not in st.session_state:
        st.session_state.admin_logged_in = False
    if st.session_state.admin_logged_in:
        return True

    if "admin" not in st.secrets or "password" not in st.secrets["admin"]:
        st.error(
            "🔴 No hay password configurado en `st.secrets['admin']['password']`. "
            "El editor está deshabilitado hasta que se configure."
        )
        return False

    with st.sidebar:
        st.header("🔐 Acceso administrador")
        password = st.text_input(
            "Contraseña:", type="password", key="admin_password_input"
        )
        if st.button("Ingresar", type="primary"):
            if password == st.secrets["admin"]["password"]:
                st.session_state.admin_logged_in = True
                st.rerun()
            else:
                st.error("❌ Contraseña incorrecta")
    return False


if not _password_correcto():
    st.info(
        """
        Esta sección está **restringida**. Solo el equipo de tesis puede editar
        los datos sintéticos directamente desde el navegador. Los cambios se
        guardan en Google Sheets y se mantienen entre sesiones.

        👉 Si sos el administrador, ingresá tu contraseña en el panel lateral.

        Si querés ver los datos sin editarlos, andá a **"📂 Datos crudos"**
        (read-only, sin password).
        """
    )
    st.stop()

# ---------------------------------------------------------------------
# Acceso autenticado
# ---------------------------------------------------------------------
with st.sidebar:
    st.success(f"✅ Sesión admin activa")
    if st.button("🚪 Cerrar sesión"):
        st.session_state.admin_logged_in = False
        st.rerun()

# Importamos sheets_io recién acá para que un usuario no autenticado no
# dispare la conexión a Google.
try:
    from src.sheets_io import (  # noqa: E402
        escribir_hoja, inicializar_sheet_con_sinteticos, leer_hoja,
        listar_hojas,
    )
except Exception as exc:  # noqa: BLE001
    st.error(f"❌ Error importando módulo de Sheets: {exc}")
    st.stop()


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------
@st.cache_data(ttl=60, show_spinner="📥 Leyendo Google Sheets...")
def _cargar_hoja_cached(nombre: str) -> pd.DataFrame:
    return leer_hoja(nombre)


def _invalidar_cache_lectura():
    _cargar_hoja_cached.clear()


# ---------------------------------------------------------------------
# Estado del Sheet (vacío o con datos)
# ---------------------------------------------------------------------
try:
    hojas_disponibles = listar_hojas()
except Exception as exc:  # noqa: BLE001
    st.error(
        f"❌ No se pudo conectar a Google Sheets: {exc}\n\n"
        "Revisá que los secrets `[google_sheets]` estén bien configurados "
        "y que el service account tenga permiso de Editor sobre el Sheet."
    )
    st.stop()

st.success(
    f"✅ Conectado al Sheet · pestañas detectadas: {', '.join(hojas_disponibles)}"
)

# Verificamos si la hoja principal "Datos" tiene contenido
try:
    df_datos_check = _cargar_hoja_cached("Datos")
except Exception:  # noqa: BLE001
    df_datos_check = pd.DataFrame()

if df_datos_check.empty:
    st.warning(
        "⚠️ El Sheet está vacío. Necesita inicializarse con los datos "
        "sintéticos antes de poder editar."
    )
    if st.button("🚀 Inicializar Sheet con datos sintéticos",
                  type="primary"):
        with st.spinner("Generando y subiendo datos sintéticos..."):
            try:
                resumen = inicializar_sheet_con_sinteticos()
                _invalidar_cache_lectura()
                st.success(
                    f"✅ Sheet inicializado. Filas escritas por hoja: {resumen}"
                )
                time.sleep(1.5)
                st.rerun()
            except Exception as exc:  # noqa: BLE001
                st.error(f"❌ Falló la inicialización: {exc}")
    st.stop()

# ---------------------------------------------------------------------
# Editor por hoja
# ---------------------------------------------------------------------
st.markdown(
    """
    Editá las celdas directamente abajo. Los cambios **no se guardan
    automáticamente** — usá el botón **💾 Guardar** al final de cada hoja
    para persistir al Sheet.
    """
)

tabs = st.tabs([f"📋 {h}" for h in hojas_disponibles])

for tab, nombre_hoja in zip(tabs, hojas_disponibles):
    with tab:
        df_hoja = _cargar_hoja_cached(nombre_hoja)
        st.caption(
            f"Filas: {len(df_hoja)} · Columnas: {len(df_hoja.columns)}"
        )

        # st.data_editor permite editar inline; respeta tipos numéricos
        df_editado = st.data_editor(
            df_hoja,
            num_rows="dynamic" if nombre_hoja == "Datos" else "fixed",
            use_container_width=True,
            key=f"editor_{nombre_hoja}",
            height=500,
        )

        col_a, col_b = st.columns([1, 4])
        with col_a:
            guardar = st.button(
                f"💾 Guardar '{nombre_hoja}'",
                key=f"save_{nombre_hoja}",
                type="primary",
            )
        with col_b:
            if not df_hoja.equals(df_editado):
                st.info(
                    "✏️ Hay cambios sin guardar en esta hoja. "
                    "Click en 'Guardar' para persistirlos al Sheet."
                )

        if guardar:
            with st.spinner(f"Guardando '{nombre_hoja}' en Google Sheets..."):
                try:
                    escribir_hoja(nombre_hoja, df_editado)
                    _invalidar_cache_lectura()
                    st.success(
                        f"✅ Hoja '{nombre_hoja}' actualizada correctamente."
                    )
                    time.sleep(1)
                    st.rerun()
                except Exception as exc:  # noqa: BLE001
                    st.error(f"❌ Error guardando: {exc}")

# ---------------------------------------------------------------------
# Re-entrenar modelo
# ---------------------------------------------------------------------
st.markdown("---")
st.subheader("🤖 Re-entrenar modelo con los datos actuales del Sheet")
st.caption(
    "Lee el Sheet, regenera el dataset, entrena el modelo y proyecta "
    "2025-2030 con los 3 escenarios. Los outputs quedan en memoria de "
    "esta sesión hasta el próximo reboot del server."
)

if st.button("⚡ Ejecutar re-entrenamiento"):
    progreso = st.progress(0, text="Iniciando...")
    try:
        progreso.progress(15, text="Leyendo hoja 'Datos' del Sheet...")
        df_maestro = _cargar_hoja_cached("Datos")

        progreso.progress(35, text="Construyendo features...")
        from src import config  # noqa: E402
        from src.feature_engineering import construir_features  # noqa: E402
        from src.model import entrenar_y_seleccionar  # noqa: E402
        from src.projection import (  # noqa: E402
            construir_resumen_nacional, generar_proyecciones,
            proyectar_features_completo,
        )

        df_hist = df_maestro[df_maestro["Año"] <= config.ANIO_FIN_HISTORICO].copy()
        df_features = construir_features(df_hist, incluir_lag=True)

        progreso.progress(55, text="Entrenando modelos (k-fold CV)...")
        resultado = entrenar_y_seleccionar(df_features, guardar_metricas=False)

        progreso.progress(75, text="Generando proyecciones 2025-2030...")
        df_completo = proyectar_features_completo(df_hist)
        df_proy = generar_proyecciones(resultado, df_completo)
        df_resumen = construir_resumen_nacional(df_proy)

        progreso.progress(100, text="¡Listo!")
        time.sleep(0.5)
        progreso.empty()

        st.success(
            f"✅ Re-entrenamiento completo · "
            f"Modelo: **{resultado.nombre_mejor}** · "
            f"MAE-CV: **{resultado.metricas[resultado.nombre_mejor].mae_cv:.3f}**"
        )

        # Guardamos en session_state para que el resto de la app pueda
        # consultarlo durante esta sesión
        st.session_state["proyeccion_actual"] = df_proy
        st.session_state["resumen_actual"] = df_resumen
        st.session_state["modelo_actual"] = resultado

        c1, c2 = st.columns(2)
        with c1:
            st.metric("Filas proyección", len(df_proy))
        with c2:
            st.metric("Provincias cubiertas", df_proy["Provincia"].nunique())

        st.dataframe(df_resumen, use_container_width=True, hide_index=True)

    except Exception as exc:  # noqa: BLE001
        progreso.empty()
        st.exception(exc)
