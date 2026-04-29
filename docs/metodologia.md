# Metodología

## 1. Marco general

Este documento describe el enfoque científico utilizado para proyectar la cantidad de donantes voluntarios de sangre en las 24 jurisdicciones argentinas al año 2030. La meta de referencia es la **autosuficiencia hemoterápica** definida por la Organización Mundial de la Salud: **30 donaciones por cada 1.000 habitantes**.

El presente proyecto se enmarca en una **tesis de grado** y combina técnicas de aprendizaje supervisado con una estrategia de proyección basada en escenarios.

## 2. Diseño del estudio

| Aspecto | Detalle |
|---------|---------|
| Tipo de estudio | Observacional retrospectivo con proyección prospectiva |
| Unidad de análisis | Jurisdicción × año |
| Período histórico | 2015 – 2024 (10 años) |
| Período de proyección | 2025 – 2030 (6 años) |
| Total de observaciones de entrenamiento | 240 (24 provincias × 10 años) |
| Variable target | `Tasa_Donacion_x1000` (donaciones por 1.000 habitantes) |

## 3. Fuentes de datos

| Fuente | Variables aportadas |
|--------|---------------------|
| **INDEC** — Censo Nacional 2022, EPH | Demografía, educación, ingreso, desempleo, cobertura de salud |
| **Plan Nacional de Sangre** (Min. Salud) | Donantes anuales, centros, campañas |
| **OPS/PAHO** | Tasas regionales y benchmarks LATAM |
| **Boletín Integrado de Vigilancia** | Casos de dengue (variable epidemiológica) |
| **World Bank Open Data** | Indicadores macro de validación |

> ⚠️ El target (`Tasa_Donacion_x1000`, `Donantes_Anuales`) sigue siendo **sintético** hasta obtener respuesta del Plan Nacional de Sangre. Las variables predictoras se enriquecen progresivamente con datos reales (ver § 3.1).

### 3.1. Integración REFES (Capa 1 — Establecimientos)

A partir de la versión 0.2.0, la variable `Centros_Hemoterapia` puede ser reemplazada por datos reales del **Registro Federal de Establecimientos de Salud (REFES)**, dataset oficial publicado por el Ministerio de Salud en `datos.salud.gob.ar`.

**Flujo de identificación:**
1. Se descargan todos los snapshots disponibles (2018, 2019, 2020, 2021, 2022, 2024, 2025, 2026 — gap en 2023).
2. Se filtran establecimientos cuya tipología oficial es **"Bancos de Sangre"** o cuyo nombre contiene "hemoterapia", "hemocentro", "banco de sangre" o "servicio transfusional", excluyendo falsos positivos (hemodiálisis, hemodinamia).
3. Se agrega por jurisdicción y año.
4. Para años sin snapshot (ej. 2023) se interpola linealmente entre vecinos.
5. Para combinaciones (provincia, año) sin cobertura se mantiene el valor sintético como **fallback documentado** en la columna `Fuente_Centros`.

**Cobertura observada:** ~55 % de las filas usan dato REFES real, 21 de 24 jurisdicciones cubiertas. La Rioja, Río Negro y Santa Cruz no tienen establecimientos identificables en REFES como bancos de sangre — sus servicios probablemente están integrados a hospitales generales sin la palabra "hemoterapia" en el nombre. Esta limitación es inherente al registro y se reporta transparentemente en `data/output/cobertura_refes.csv`.

## 4. Variables explicativas

Las variables predictoras se agrupan en cuatro bloques teóricos:

### 4.1. Demográficas
- `Población_Total`
- `Población_18_65` (rango etario elegible)
- `Densidad_Poblacional`

### 4.2. Socioeconómicas
- `Pct_Educacion_Superior`
- `Indice_Ingreso_Promedio`
- `Tasa_Desempleo`
- `Pct_Cobertura_Salud`

### 4.3. Sistema sanitario
- `Centros_Hemoterapia`
- `Campañas_Donacion_Anuales`

### 4.4. Epidemiológicas
- `Casos_Dengue_Anual` (proxy de carga sanitaria competitiva)

### 4.5. Variables derivadas (feature engineering)
- `Centros_x_100k_hab` — densidad de centros por habitantes.
- `Campañas_per_capita` — esfuerzo institucional normalizado.
- `Casos_Dengue_x_1000_hab` — presión epidemiológica relativa.
- `Pct_Pob_18_65` — proporción elegible.
- `Es_Pandemia` — indicador binario para 2020–2021.
- `Tasa_Donacion_Lag1` — autocorrelación temporal.
- One-hot encoding de `Region` (Centro, NOA, NEA, Cuyo, Patagonia).

## 5. Modelo predictivo

### 5.1. Algoritmos evaluados

Se compararon dos algoritmos basados en árboles de decisión, robustos frente a no linealidades, interacciones y outliers:

1. **Random Forest Regressor** (200 árboles, `max_depth=12`).
2. **Gradient Boosting Regressor** (300 etapas, `learning_rate=0.05`).

### 5.2. Validación

- **Estrategia:** K-Fold Cross Validation con k=5, shuffle activado, `random_state=42`.
- **Métrica primaria:** Mean Absolute Error (MAE).
- **Métricas secundarias:** R² y RMSE sobre el conjunto de entrenamiento.
- **Selección automática:** se elige el modelo con menor MAE-CV.

### 5.3. Reproducibilidad

- Random state fijo en todas las funciones estocásticas.
- Versiones específicas en `requirements.txt` (`==`).
- Tests automatizados con `pytest`.

## 6. Generación de proyecciones

### 6.1. Proyección de variables predictoras

Para 2025–2030, las features se proyectan mediante **regresión lineal sobre los últimos 5 años** de cada variable, con clipping defensivo en límites razonables (ej. desempleo entre 1% y 30%).

### 6.2. Escenarios

| Escenario | Ajustes sobre features 2025-2030 |
|-----------|----------------------------------|
| **Pesimista** | -15% campañas · +20% desempleo · +50% dengue |
| **Base** | Predicción directa sin ajustes |
| **Optimista** | +50% campañas · +10% educación · +15% centros |

### 6.3. Predicción rolling

La predicción de la tasa se hace año por año:
1. Predecimos la tasa de 2025 con todas las features observadas/proyectadas.
2. Esa predicción alimenta el `Lag1` de 2026.
3. Repetir hasta 2030.

Esto preserva la dependencia temporal sin requerir el target de años futuros.

## 7. Cálculos derivados

Para cada provincia, año y escenario:

```
Donantes_Anuales = Tasa_Donacion_x1000 × Población_Total / 1000
Donantes_OMS_Necesarios = 30 × Población_Total / 1000
Brecha_Donantes = Donantes_OMS_Necesarios − Donantes_Anuales
Pct_Cumplimiento_OMS = Tasa / 30 × 100
```

## 8. Limitaciones reconocidas

1. **Calidad de datos**: el dataset sintético no captura idiosincrasias reales que sí tendrán los datos del Plan Nacional de Sangre.
2. **Extrapolación lineal de features**: simplificación que asume estabilidad de tendencias.
3. **No considera shocks externos** (nuevas pandemias, cambios estructurales de política sanitaria, conflictos sociales).
4. **Escala provincial uniforme**: ignora heterogeneidad intra-provincial.
5. **Causalidad vs correlación**: el modelo identifica asociaciones, no relaciones causales.

## 9. Trabajos futuros

- Reemplazar dataset sintético por datos oficiales (cuando se obtenga respuesta del Ministerio).
- Incorporar modelos jerárquicos / panel de datos (efectos fijos provinciales).
- Explorar redes neuronales recurrentes para series temporales.
- Validación cruzada temporal (rolling-origin) en lugar de K-Fold aleatorio.
- Análisis de sensibilidad y bandas de confianza con bootstrap.
- Triangulación con encuestas a centros de hemoterapia.

## 10. Referencias

- WHO (2023). *Blood safety and availability*. Fact sheet.
- OPS/PAHO (2023). *Suministro de sangre para transfusiones en LATAM y el Caribe*.
- INDEC (2022). *Censo Nacional de Población, Hogares y Viviendas*.
- Breiman, L. (2001). *Random Forests*. Machine Learning 45(1), 5–32.
- Friedman, J. H. (2001). *Greedy function approximation: a gradient boosting machine*. Annals of Statistics 29(5), 1189–1232.
