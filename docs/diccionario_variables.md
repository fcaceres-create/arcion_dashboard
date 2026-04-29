# Diccionario de variables

Todas las variables del dataset maestro `data/raw/dataset_donantes_argentina.xlsx` (hoja `Datos`).

## Identificadores

| Variable | Tipo | Unidad | Descripción | Fuente esperada |
|----------|------|--------|-------------|-----------------|
| `Provincia` | Texto | — | Jurisdicción argentina (24 valores: 23 provincias + CABA). | INDEC |
| `Region` | Texto | — | Región geográfica: Centro, NOA, NEA, Cuyo, Patagonia. | INDEC (categorización propia) |
| `Año` | Entero | año | Período de medición. | INDEC |

## Demográficas

| Variable | Tipo | Unidad | Descripción | Fuente esperada |
|----------|------|--------|-------------|-----------------|
| `Población_Total` | Entero | habitantes | Población total estimada al 30 de junio de cada año. | INDEC – Censo 2022 + proyecciones |
| `Población_18_65` | Entero | habitantes | Población en edad de donar (rango legal/médico de elegibilidad). | INDEC – EPH |
| `Densidad_Poblacional` | Decimal | hab/km² | Densidad por jurisdicción. | INDEC |

## Socioeconómicas

| Variable | Tipo | Unidad | Descripción | Fuente esperada |
|----------|------|--------|-------------|-----------------|
| `Pct_Educacion_Superior` | Decimal | % | Población mayor de 25 años con estudios terciarios o universitarios completos o incompletos. | INDEC – EPH |
| `Indice_Ingreso_Promedio` | Decimal | índice 0-100 | Índice normalizado del ingreso promedio del hogar (referencia: media nacional = 50). | INDEC – EPH |
| `Tasa_Desempleo` | Decimal | % | Tasa de desocupación de la población económicamente activa. | INDEC – EPH |
| `Pct_Cobertura_Salud` | Decimal | % | % de la población con obra social, prepaga o plan estatal. | INDEC – EPH |

## Sistema sanitario

| Variable | Tipo | Unidad | Descripción | Fuente esperada |
|----------|------|--------|-------------|-----------------|
| `Centros_Hemoterapia` | Entero | unidades | Cantidad de centros activos de hemoterapia en la jurisdicción. | Plan Nacional de Sangre |
| `Campañas_Donacion_Anuales` | Entero | unidades | Cantidad de campañas oficiales de promoción de donación realizadas en el año. | Plan Nacional de Sangre |

## Epidemiológicas

| Variable | Tipo | Unidad | Descripción | Fuente esperada |
|----------|------|--------|-------------|-----------------|
| `Casos_Dengue_Anual` | Entero | casos | Casos confirmados de dengue notificados al sistema de vigilancia. | Boletín Integrado de Vigilancia (Min. Salud) |

## Targets (variables a predecir)

| Variable | Tipo | Unidad | Descripción | Fuente esperada |
|----------|------|--------|-------------|-----------------|
| `Tasa_Donacion_x1000` | Decimal | donaciones / 1.000 hab | **TARGET principal**. Se calcula como `Donantes / Población × 1.000`. Solo poblada en histórico (2015-2024). | Plan Nacional de Sangre |
| `Donantes_Anuales` | Entero | personas | Cantidad absoluta de donantes voluntarios. Solo poblada en histórico. | Plan Nacional de Sangre |

## Variables derivadas (feature engineering)

Calculadas en `src/feature_engineering.py`. No están en el Excel maestro.

| Variable | Tipo | Cálculo |
|----------|------|---------|
| `Centros_x_100k_hab` | Decimal | `Centros_Hemoterapia / Población_Total × 100.000` |
| `Campañas_per_capita` | Decimal | `Campañas_Donacion_Anuales / Población_Total × 100.000` |
| `Casos_Dengue_x_1000_hab` | Decimal | `Casos_Dengue_Anual / Población_Total × 1.000` |
| `Pct_Pob_18_65` | Decimal | `Población_18_65 / Población_Total × 100` |
| `Es_Pandemia` | Binario {0, 1} | 1 si Año ∈ {2020, 2021}, 0 en otro caso |
| `Tasa_Donacion_Lag1` | Decimal | Tasa del año anterior (mismo provincia). Imputada con mediana provincial cuando no existe. |
| `Region_*` | Binario | One-hot encoding de la región (5 columnas). |

## Variables agregadas en el output del modelo

Calculadas en `src/projection.py`. Aparecen en `data/output/proyeccion_donantes_2030.csv`.

| Variable | Tipo | Cálculo |
|----------|------|---------|
| `Escenario` | Texto | `historico`, `pesimista`, `base`, `optimista` |
| `Tipo_Año` | Texto | `Histórico` o `Proyectado` |
| `Donantes_OMS_Necesarios` | Entero | `30 × Población_Total / 1000` |
| `Brecha_Donantes` | Entero | `Donantes_OMS_Necesarios − Donantes_Anuales` |
| `Pct_Cumplimiento_OMS` | Decimal | `Tasa_Donacion_x1000 / 30 × 100` |

## Notas sobre tipos y unidades

- Los **enteros poblacionales** vienen redondeados al alza/baja según corresponda; en agregaciones nacionales pueden aparecer pequeñas diferencias por redondeo.
- Las **tasas** se expresan como `donaciones / 1.000 habitantes`, no como porcentaje, siguiendo el estándar OMS.
- Los **porcentajes** se almacenan como números entre 0 y 100 (no como fracciones 0-1).
