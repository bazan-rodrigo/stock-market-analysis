---
slug: centro-de-datos
title: Centro de Datos
chapter: 6. Datos de Mercado
order: 650
roles: admin
page: /admin/data-center
---

Es el tablero de control de todo lo que el sistema calcula. Cada tarjeta es un
eslabón del [pipeline](/manual/conceptos-pipeline) y permite dispararlo a mano,
ver su estado y seguir el avance en vivo.

En el día a día no hace falta entrar: la corrida nocturna automática actualiza
precios y vuelve a correr señales y estrategias sola. Esta pantalla es para
cuando algo se salió de lo normal — la app estuvo apagada unos días, cambiaste
una definición, agregaste activos nuevos, o querés confirmar que los datos
están al día.

> **Es la pantalla de mayor impacto del sistema.** Los botones rojos borran
> historia y la reconstruyen; algunos pueden tardar horas. Leé la sección de
> operaciones largas antes de usarlos.

## Cómo funciona la pantalla

Todas las tarjetas tienen la misma estructura: una descripción, una línea de
**estado** con los números actuales, una barra de progreso, el mensaje de la
última corrida y los botones. **Solo puede correr una operación por vez**:
mientras algo está en curso todos los botones quedan deshabilitados y cualquier
intento responde *"Hay otra operación en curso"*. La exclusión cubre también los
botones de la pantalla de Actualización de precios y la corrida nocturna, que se
saltea si encuentra el sistema ocupado.

Mientras tanto, las tres tarjetas de conteo pesado —**Indicadores Técnicos**,
**Indicadores Fundamentales** y **Señales y Estrategias**— **congelan su línea
de estado** en el último valor conocido en lugar de recontar: los números
frescos llegan al terminar, así que un número que no se mueve no está mal. Las
otras tres (**Actualizar Precios**, **Actualizar Fundamentales** y **Recalcular
Sintéticos**) siguen mostrando su estado en vivo, porque su consulta es
liviana. El avance sí se muestra con detalle
—por cada indicador o etapa, cuántos van, hora de inicio, de fin y duración— y
al terminar el mensaje queda en verde con el resumen o en rojo con el error.

## Las seis tarjetas

### Actualizar Precios

Descarga precios desde las fuentes externas y, al terminar, **encadena
automáticamente** el recálculo de indicadores técnicos y de ratios
fundamentales. Es la operación que corre sola cada noche.

| Control | Qué hace |
|---|---|
| **Ejecutar** | Actualiza todos los activos, incluidos los sintéticos. |
| **Solo activos nuevos** | Limita la corrida a los activos que nunca se descargaron. Es el atajo después de importar activos: minutos en vez de mucho más. |
| **Redescargar completo** | Borra toda la historia de precios de todos los activos y la baja de nuevo desde la fuente. Pide confirmación. |
| **Ver logs** | Lleva a la pantalla de Actualización de precios, con el resultado por activo. |

La línea de estado muestra la fecha del último run, cuántos activos terminaron
bien, cuántos fallaron y el total.

### Actualizar Fundamentales

Lo mismo, con los datos trimestrales de balance de los activos que tengan una
fuente de fundamentales configurada. Encadena el recálculo de ratios al terminar
y tiene **Solo activos nuevos**, **Redescargar completo** y **Ver logs**.

### Indicadores Técnicos

| Control | Qué hace |
|---|---|
| **Ejecutar** | Recalcula la última fecha de cada activo y, de paso, completa las fechas históricas que tengan precio pero no indicador. Es la actualización incremental. |
| **Recalcular caché** | **No recalcula ningún indicador.** Reconstruye el registro interno que el sistema usa para saber qué falta y así acelerar la actualización incremental. Se usa solo si ese registro quedó inconsistente, típicamente por una edición manual desde la consola SQL. |
| **Recalcular completo** | Borra toda la historia de indicadores y la rehace desde el primer precio. Pide confirmación. |

### Indicadores Fundamentales

**Ejecutar** recalcula P/E, P/B, márgenes, ROIC y demás ratios para hoy y
completa las fechas históricas que no los tengan. **Recalcular completo** rehace
todo el historial de ratios a partir de los trimestres ya almacenados —no
descarga nada de la fuente— y pide confirmación.

### Recalcular Sintéticos

Recalcula los precios de los activos sintéticos (ratios, índices, conversiones
de moneda) a partir de sus componentes. **Ejecutar** hace solo el delta y
mantiene el historial; **Recalcular completo** lo borra y lo rehace desde cero.
Es lo que hay que correr si cambiaste la fórmula de un sintético.

### Señales y Estrategias

La tarjeta más delicada: corre el tramo final del pipeline (agregados de grupo →
señales → estrategias) fecha por fecha, sobre todo el universo.

| Control | Qué hace |
|---|---|
| **Ejecutar** | Calcula las fechas que tienen precios pero no señales y recalcula siempre la última. Es lo que llena los huecos si la corrida nocturna estuvo apagada. |
| **Horizonte (días)** | Limita la operación a los últimos N días. **Vacío significa toda la historia.** |
| Selector de alcance | Restringe el trabajo a **una** estrategia o a **una** señal. Vacío = todas. |
| **Incluir señales** | Solo tiene efecto con alcance de estrategia. Apagado, las señales no se vuelven a evaluar (se leen las guardadas) y se reconstruye únicamente el resultado de la estrategia: mucho más rápido. Dejalo prendido si cambiaste señales o indicadores. |
| **Recalcular completo** | Reescribe todas las fechas del horizonte. Es lo que hay que usar tras cambiar la definición de una señal o de una estrategia. |

El horizonte y el alcance aplican a **los dos** botones, no solo al rojo.

> Antes de ejecutar, el cuadro de confirmación de **Recalcular completo** se
> reescribe solo para describir exactamente lo que va a pasar con la
> combinación que elegiste de alcance, horizonte e **Incluir señales**.
> Leelo: es la mejor defensa contra recalcular toda la historia sin querer.

Necesita los indicadores ya calculados. Y es la tarjeta que hay que usar —en
modo **Recalcular completo**— cuando incorporás activos nuevos: como el ranking
es transversal, la actualización incremental no los suma a la historia pasada
(ver [el pipeline](/manual/conceptos-pipeline)).

## Operaciones largas y en qué orden ejecutarlas

Las operaciones incrementales (**Ejecutar**) suelen resolverse en minutos. Las
completas escalan con la cantidad de activos y los años de historia: sobre un
universo grande y sin horizonte pueden llevar **horas**, y durante todo ese
tiempo el resto del sistema queda bloqueado para escrituras. El porqué de esos
tiempos —qué borra un recálculo, por qué se borra por ventanas— está explicado
en [Deltas, recálculos y borrado masivo](/manual/deltas-y-borrado-masivo).

1. **Acotá siempre que puedas.** Antes de un recálculo total de señales, probá
   con un horizonte de 90 días o con el alcance puesto en la única estrategia
   que tocaste.
2. **Lanzá lo pesado cuando nadie esté usando la app**, y contá con que la
   corrida nocturna se va a saltear si todavía está corriendo.
3. **Respetá el orden del pipeline.** Reconstruir señales sobre indicadores
   viejos da resultados viejos.

Si tenés que reconstruir todo de cero, el orden es **Precios → Fundamentales →
Sintéticos → Indicadores Técnicos → Indicadores Fundamentales → Señales y
Estrategias**: cada paso consume la salida del anterior. Como Precios y
Fundamentales ya encadenan solos el recálculo incremental de sus indicadores, en
muchos casos alcanza con correr esos dos y cerrar con Señales y Estrategias.

## Escrituras por corrida (diagnóstico)

Al pie de la pantalla hay un panel que registra, para cada corrida que
lanzaste, **cuánta información insertó y cuánta actualizó** en la base — medido
automáticamente, sin que tengas que hacer nada. Cada corrida aparece con su
horario, la cantidad de activos y un veredicto:

- **✓ normal**: la corrida escribió lo esperable (en una actualización
  incremental, alrededor de una o dos actualizaciones por activo).
- **⚠ revisión amplia**: escribió bastante más — pasa de forma legítima cuando
  llega un precio nuevo y los indicadores que dependen de toda la historia
  (percentiles, zonas) reclasifican fechas viejas. No es un error.
- **✗ revisar**: un volumen de actualizaciones desproporcionado, señal de que
  algo está escribiendo de más. Si aparece seguido, avisale a quien mantiene
  el sistema.

Dos aclaraciones: el panel funciona solo cuando la base es PostgreSQL (en
otros motores dice "no disponible"), y si dos procesos escriben a la vez sus
números se mezclan — mirálo con una corrida por vez. El registro se limpia
cuando la app se reinicia: es un diagnóstico del momento, no un historial.
