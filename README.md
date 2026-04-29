# Proyección de Donantes de Sangre en Argentina (2025–2030)

![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Status](https://img.shields.io/badge/status-academic--prototype-orange)
![Streamlit](https://img.shields.io/badge/UI-Streamlit-red)
![PowerBI](https://img.shields.io/badge/Dashboard-PowerBI-yellow)

> Aplicación de análisis predictivo desarrollada como **trabajo final de tesis**, cuyo objetivo es proyectar la cantidad de donantes voluntarios de sangre en las 24 jurisdicciones argentinas hasta el año **2030**, comparando los resultados contra la **meta de la Organización Mundial de la Salud (OMS): 30 donaciones por cada 1.000 habitantes**.

---

## 1. Motivación

Argentina actualmente registra una tasa de donación de aproximadamente **19 donaciones / 1.000 habitantes** (OPS, 2023), lejos del óptimo recomendado por la OMS para alcanzar la **autosuficiencia hemoterápica** (30 / 1.000). El presente proyecto integra técnicas de **machine learning supervisado** (Random Forest y Gradient Boosting) con un dataset multi-variable de origen oficial (INDEC, Plan Nacional de Sangre, OPS, World Bank) para responder a tres preguntas:

1. ¿Cuál es la trayectoria proyectada de donantes en cada jurisdicción al año 2030?
2. ¿Qué brecha existirá frente al óptimo OMS bajo escenarios *pesimista*, *base* y *optimista*?
3. ¿Qué variables (campañas, educación, cobertura, centros) tienen mayor impacto en la tasa?

---

## 2. Stack tecnológico

| Capa | Tecnología |
|------|-----------|
| Lenguaje | Python 3.11+ |
| ML / datos | pandas, numpy, scikit-learn, openpyxl |
| Visualización | matplotlib, seaborn, plotly |
| App web | Streamlit |
| Dashboard ejecutivo | Power BI Desktop |
| Testing | pytest |
| Control de versiones | Git + GitHub |

---

## 3. Instalación

### 3.1. Clonar el repositorio

```bash
git clone https://github.com/<usuario>/proyeccion-donantes-argentina.git
cd proyeccion-donantes-argentina
```

### 3.2. Crear entorno virtual

**Windows (PowerShell):**

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3 -m venv venv
source venv/bin/activate
```

### 3.3. Instalar dependencias

```bash
pip install --upgrade pip

# Solo lo necesario para correr la app
pip install -r requirements.txt

# Adicional para desarrollo (tests, notebooks)
pip install -r requirements-dev.txt
```

---

## 4. Ejecución

### 4.1. Pipeline completo (genera dataset, entrena modelo y exporta resultados)

```bash
# Modo sintético (por defecto)
python scripts/run_pipeline.py

# Modo enriquecido con datos reales del Ministerio de Salud (REFES)
python scripts/run_pipeline.py --usar-refes
```

Con `--usar-refes` el pipeline descarga el **Registro Federal de Establecimientos de Salud** (`datos.salud.gob.ar`), filtra los centros de hemoterapia / bancos de sangre y reemplaza la columna sintética con el conteo real por jurisdicción. Las jurisdicciones / años sin cobertura caen al sintético y se documentan en `data/output/cobertura_refes.csv`.

Salida esperada en `data/output/`:
- `proyeccion_donantes_2030.csv` (long format, listo para Power BI)
- `resumen_nacional.csv`
- `model_metrics.json`
- `cobertura_refes.csv` (solo si se usó `--usar-refes`)

### 4.2. Aplicación Streamlit

```bash
streamlit run app/streamlit_app.py
```

La app se abrirá en `http://localhost:8501`.

### 4.3. Tests

```bash
pytest tests/ -v
```

### 4.4. Power BI

Ver [`powerbi/instrucciones_powerbi.md`](powerbi/instrucciones_powerbi.md) para conectar el CSV al template y crear las medidas DAX recomendadas.

---

## 5. Estructura del proyecto

```
proyeccion-donantes-argentina/
├── data/                  # Datos crudos, procesados y outputs del modelo
├── src/                   # Código fuente: ML, ETL, APIs
├── notebooks/             # Notebooks exploratorios
├── app/                   # Aplicación Streamlit
├── scripts/               # Pipelines orquestados
├── powerbi/               # Templates e instrucciones PBI
├── tests/                 # Tests unitarios
└── docs/                  # Documentación académica
```

---

## 6. Roadmap

- [x] Dataset sintético funcional (24 provincias × 16 años)
- [x] Modelo predictivo con validación cruzada
- [x] Aplicación Streamlit interactiva
- [x] Exportación a Power BI
- [x] Integración REFES (Min. Salud) — centros de hemoterapia reales por provincia
- [ ] Reemplazar dataset sintético por datos oficiales del **Plan Nacional de Sangre** (pendiente respuesta del Ministerio de Salud)
- [ ] Capa 2 — Vigilancia epidemiológica real (dengue, HIV, hepatitis)
- [ ] Capa 3 — Recursos humanos en salud + estadísticas vitales
- [ ] Publicación de la app en Streamlit Community Cloud
- [ ] Validación con expertos del INCUCAI

---

## 7. Créditos y referencias

- **Organización Mundial de la Salud (OMS)** — *Blood safety and availability*, fact sheet 2023.
- **Organización Panamericana de la Salud (OPS/PAHO)** — *Suministro de sangre para transfusiones en los países de Latinoamérica y el Caribe*, 2023.
- **INDEC** — Censo Nacional de Población, Hogares y Viviendas 2022.
- **Ministerio de Salud de la Nación Argentina** — Plan Nacional de Sangre.

> Proyecto académico desarrollado en el marco de la tesis de grado. Los datos sintéticos generados por este repositorio **no representan estadísticas oficiales** y se utilizan exclusivamente para fines metodológicos hasta tanto se obtengan datos públicos validados.

---

## 8. Licencia

MIT License — ver [`LICENSE`](LICENSE).
