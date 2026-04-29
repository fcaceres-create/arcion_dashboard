# Conexión y configuración de Power BI

Este documento explica paso a paso cómo conectar el output del pipeline a Power BI Desktop y crear el dashboard ejecutivo.

## 1. Pre-requisitos

- **Power BI Desktop** (gratuito): https://powerbi.microsoft.com/desktop/
- Haber ejecutado el pipeline al menos una vez:
  ```bash
  python scripts/run_pipeline.py
  python scripts/export_powerbi.py
  ```
- Verificar que existan los siguientes archivos en `data/output/`:
  - `powerbi_proyeccion.csv` (tabla de hechos)
  - `powerbi_dim_provincia.csv` (dimensión)
  - `powerbi_dim_anio.csv` (dimensión)

## 2. Conexión inicial

1. Abrir Power BI Desktop → **Inicio → Obtener datos → Texto/CSV**.
2. Seleccionar `data/output/powerbi_proyeccion.csv`.
3. En el preview, **verificar la codificación**: debe ser **65001 — Unicode (UTF-8)** para que los acentos se vean correctamente. El archivo se exporta con BOM, por lo que Power BI debería detectarlo automáticamente.
4. Click en **Transformar datos** para abrir Power Query Editor.

## 3. Transformaciones recomendadas en Power Query

En el editor de Power Query, antes de cargar la tabla:

1. **Tipos de datos** (verificar que estén bien detectados):
   - `Año`: Número entero
   - `Población_Total`, `Donantes_Anuales`, `Brecha_Donantes`: Número entero
   - `Tasa_Donacion_x1000`, `Pct_Cumplimiento_OMS`: Número decimal
   - `Provincia`, `Region`, `Escenario`, `Tipo_Año`, `Categoria_Cumplimiento`: Texto
2. Cargar también `powerbi_dim_provincia.csv` y `powerbi_dim_anio.csv` como tablas separadas.
3. Click en **Cerrar y aplicar**.

## 4. Modelo de datos

En la vista **Modelo**, crear las siguientes relaciones:

| Tabla origen | Columna | Tabla destino | Columna | Cardinalidad |
|--------------|---------|---------------|---------|--------------|
| `powerbi_proyeccion` | `Provincia` | `powerbi_dim_provincia` | `Provincia` | Muchos a uno |
| `powerbi_proyeccion` | `Año` | `powerbi_dim_anio` | `Año` | Muchos a uno |

## 5. Medidas DAX recomendadas

Crear las siguientes medidas en la tabla `powerbi_proyeccion`:

```dax
-- =========================
-- MEDIDAS BASE
-- =========================

Total Donantes =
SUM ( 'powerbi_proyeccion'[Donantes_Anuales] )

Total Población =
SUM ( 'powerbi_proyeccion'[Población_Total] )

Total Donantes OMS Necesarios =
SUM ( 'powerbi_proyeccion'[Donantes_OMS_Necesarios] )

Brecha Absoluta =
[Total Donantes OMS Necesarios] - [Total Donantes]

-- =========================
-- TASAS Y CUMPLIMIENTO
-- =========================

Tasa Nacional x1000 =
DIVIDE ( [Total Donantes], [Total Población] ) * 1000

% Cumplimiento OMS =
DIVIDE ( [Tasa Nacional x1000], 30 )

% Brecha vs OMS =
1 - [% Cumplimiento OMS]

-- =========================
-- COMPARATIVAS TEMPORALES
-- =========================

Donantes Año Anterior =
CALCULATE (
    [Total Donantes],
    DATEADD ( 'powerbi_dim_anio'[Año], -1, YEAR )
)

Variación Interanual % =
VAR Actual = [Total Donantes]
VAR Anterior = [Donantes Año Anterior]
RETURN DIVIDE ( Actual - Anterior, Anterior )

-- =========================
-- POR ESCENARIO
-- =========================

Donantes Escenario Base =
CALCULATE (
    [Total Donantes],
    'powerbi_proyeccion'[Escenario] IN { "historico", "base" }
)

Donantes Escenario Optimista =
CALCULATE (
    [Total Donantes],
    'powerbi_proyeccion'[Escenario] IN { "historico", "optimista" }
)

Donantes Escenario Pesimista =
CALCULATE (
    [Total Donantes],
    'powerbi_proyeccion'[Escenario] IN { "historico", "pesimista" }
)

-- =========================
-- INDICADORES CRÍTICOS
-- =========================

Provincias en Cumplimiento =
CALCULATE (
    DISTINCTCOUNT ( 'powerbi_proyeccion'[Provincia] ),
    'powerbi_proyeccion'[Tasa_Donacion_x1000] >= 30
)

Provincias en Estado Crítico =
CALCULATE (
    DISTINCTCOUNT ( 'powerbi_proyeccion'[Provincia] ),
    'powerbi_proyeccion'[Pct_Cumplimiento_OMS] < 50
)

Meta OMS x1000 = 30
```

## 6. Visualizaciones sugeridas

### 6.1. Página "Resumen Ejecutivo"
- **Tarjetas KPI**: Tasa Nacional x1000, % Cumplimiento OMS, Brecha Absoluta, Provincias en Cumplimiento.
- **Gráfico de líneas**: `Tasa Nacional x1000` por `Año`, segmentado por `Escenario`. Agregar línea constante `Meta OMS x1000`.
- **Mapa de Argentina** (visual nativo o ArcGIS): coloreado por `Tasa_Donacion_x1000` para el año filtrado.

### 6.2. Página "Detalle Provincial"
- **Slicer**: `Provincia` (lista) + `Escenario` (botones).
- **Gráfico de barras**: `Tasa_Donacion_x1000` por `Año`, una serie por escenario.
- **Tabla**: Donantes vs OMS Necesarios vs Brecha por año.

### 6.3. Página "Análisis Comparativo"
- **Heatmap**: `Provincia` (filas) × `Año` (columnas), valor = `% Cumplimiento OMS`.
- **Ranking**: Top y bottom 5 provincias en 2030.
- **Scatter**: `Pct_Educacion_Superior` vs `Tasa_Donacion_x1000` (validación de hipótesis).

## 7. Consejos finales

- **Refresh automático**: si trabajás localmente, el refresh es manual (Inicio → Actualizar). Para automatizar, publicar a Power BI Service y configurar **Programación de actualización**.
- **Formato de números**: en Opciones → Configuración regional, elegir **Español (Argentina)** para que los miles se muestren con punto (`1.234.567`) y los decimales con coma.
- **Colores corporativos**: usar la paleta de la tesis (rojos #B71C1C para alertas, azules #2563EB para neutros, verdes #16A34A para cumplimiento).
- **Exportar a PDF**: Inicio → Exportar → PDF, ideal para anexar al documento de tesis.

## 8. Solución de problemas

| Problema | Solución |
|----------|----------|
| Acentos se ven como `Crítico` | Verificar que el archivo tenga BOM UTF-8 (regenerarlo con `python scripts/export_powerbi.py`). |
| El mapa no reconoce provincias | Asegurarse de tener la columna `Provincia` con escritura exacta del listado oficial INDEC, y configurar la categoría de datos como "Provincia/Estado". |
| Las medidas dan 0 | Verificar las relaciones del modelo (vista Modelo). |
