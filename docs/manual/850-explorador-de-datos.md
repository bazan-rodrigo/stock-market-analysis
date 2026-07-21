---
slug: explorador-de-datos
title: Explorador de datos
chapter: 8. Administración
order: 850
roles: admin
page: /admin/data-explorer
---

Lectura cruda de los datos internos del sistema —indicadores, fundamentales,
señales, scores de grupo, resultados de estrategias— sin escribir una sola línea
de SQL.

**Es de solo lectura.** No hay forma de modificar nada desde acá, y esa es
justamente su ventaja sobre la [Consola SQL](/manual/consola-sql): sirve para lo
mismo en el 90% de los casos, sin ningún riesgo.

## Cómo se usa

Primero elegís el **Conjunto de datos** que querés ver. Según cuál elijas, la
pantalla muestra los filtros que ese conjunto necesita y esconde los que no
aplican:

| Filtro | Aparece cuando |
|---|---|
| **Indicador** | Estás viendo series de indicadores. Solo lista los que guardan historia. |
| **Señal** | Estás viendo valores de señales. |
| **Estrategia** | Estás viendo resultados de estrategias. |
| **Tipo de grupo** y **Grupo** | Estás viendo agregados de grupo (sector, mercado, industria, país o tipo de instrumento). |
| **Activo** | El conjunto es por activo. |

Los filtros que no aplican no se muestran, así que si un control que esperabas
no aparece, es porque el conjunto elegido no lo usa.

El resultado se puede **exportar a CSV** para analizarlo aparte.

> **El selector de indicadores solo lista los que guardan serie histórica.** Un
> indicador del que solo se conserva el valor vigente no aparece acá — no es un
> error, es que no hay serie que mostrar.

## Para qué sirve

Es la herramienta de diagnóstico cuando **una pantalla de análisis muestra algo
que no cierra** y querés ver el dato de origen sin intermediarios.

Casos típicos:

- **Un activo tiene un score raro.** Mirás los valores de cada señal que compone
  la estrategia y encontrás cuál está tirando el promedio.
- **Un indicador se ve mal en el gráfico.** Comparás la serie cruda contra lo
  que dibuja el gráfico para saber si el problema es el dato o la visualización.
- **Un agregado de sector no coincide con la intuición.** Mirás la serie cruda
  del score del grupo, fecha por fecha, y cuántos activos entraron en el
  promedio en cada una.
- **Necesitás los datos afuera.** Exportás a CSV y seguís en una planilla.

## Cuál elegir: este o la consola SQL

| | Explorador | [Consola SQL](/manual/consola-sql) |
|---|---|---|
| **Riesgo** | Ninguno, solo lectura | Puede modificar y borrar |
| **Requiere saber SQL** | No | Sí |
| **Alcance** | Los conjuntos previstos | Cualquier consulta |

Empezá siempre por acá. La consola queda para lo que este no cubre.

Para revisar precios en particular hay una pantalla dedicada y más cómoda:
[Visualizador de precios](/manual/visualizador-de-precios).
