# Template Power BI (.pbit)

Este placeholder representa la ubicación esperada del archivo `dashboard_donantes.pbit`.

> El template binario `.pbit` se debe **crear directamente en Power BI Desktop** una vez configuradas las relaciones, medidas y visualizaciones descritas en `instrucciones_powerbi.md`. Se exporta vía:
>
> **Archivo → Exportar → Plantilla de Power BI**
>
> y se guarda en esta carpeta con el nombre `dashboard_donantes.pbit`. Al ser un binario, no se versiona en este repositorio público sino que se distribuye como release adjunto.

## Pasos para regenerar el template desde cero

1. Abrir Power BI Desktop.
2. Conectar a `data/output/powerbi_proyeccion.csv` siguiendo `instrucciones_powerbi.md`.
3. Crear las medidas DAX recomendadas.
4. Construir las visualizaciones de las páginas Resumen, Detalle Provincial y Análisis Comparativo.
5. Eliminar los datos antes de exportar:
   - **Inicio → Transformar datos → Editor de consultas → Cerrar y aplicar** después de **filtrar todas las filas**.
   - Esto reduce el tamaño del template a < 1MB.
6. **Archivo → Exportar → Plantilla de Power BI** → guardar como `dashboard_donantes.pbit`.

El consumidor del template solo necesitará abrirlo y apuntar a su CSV local.
