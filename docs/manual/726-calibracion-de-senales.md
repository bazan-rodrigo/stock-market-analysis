---
slug: calibracion-de-senales
title: Calibración — elegir los cortes de una señal con datos
chapter: 7. Configuración
order: 726
roles: analista
page: /admin/calibracion
---

Una señal traduce un indicador a un puntaje de −100 a +100, y para eso hay que
elegir dónde empieza cada extremo. Esta pantalla muestra **dónde están los
activos de verdad**, para que esos cortes salgan de los datos y no de la
intuición.

El problema que resuelve es que una señal mal escalada **no se rompe: se queda
muda**. Si el rango es más angosto que los datos, un montón de activos queda
pegado en +100 o en −100 y entre ellos la señal deja de ordenar; si es
demasiado ancho, se apiñan todos cerca del cero y pasa lo mismo. En los dos
casos el ranking sale igual de "bien" y nada avisa.

Acá no se guarda nada. El número se escribe en
[Señales](/manual/configuracion-senales), que es el único lugar donde se define
una señal.

## Cómo se usa

**1. Elegí el indicador.** Si hay una señal definida sobre él, la pantalla la
toma sola: el catálogo tiene una sola señal por indicador (ver
[El catálogo de señales](/manual/catalogo-de-senales)).

**2. Elegí las fechas.** Podés poner varias, separadas por coma. Vacío = la
última fecha con precios cargados.

> **Poner varias fechas es el punto de esta pantalla.** Los retornos del mes,
> del trimestre y del año se reinician con el calendario, así que su dispersión
> crece a lo largo del período: una escala que recorta el 10% a mitad de camino
> puede recortar el 30% al final. Con una sola fecha ese defecto es invisible.
> Para esos tres, mirá siempre un período completo — un 31 de diciembre para el
> anual, un cierre de trimestre para el trimestral.

**3. Escribí una escala tentativa** en min y max, o traé la que la señal ya
tiene con el botón. El min puede ser mayor que el max: así se invierte una
señal.

**4. Mirá los dos gráficos.**

- **El de la izquierda** superpone la curva de la señal sobre el histograma del
  indicador, en el mismo eje. Ahí se ve de una si los cortes caen donde hay
  activos o donde no hay nadie. Las dos líneas punteadas son el min y el max.
- **El de la derecha** es el puntaje que saldría. Los dos amontonamientos en los
  extremos son la saturación: cuanto más altos, más activos dejaron de
  ordenarse entre sí.

**5. Llevá el número al editor** con el botón, que abre la señal con la escala
cargada. Todavía no guardó nada: revisás y guardás ahí.

## Qué mirar en las tablas

**Cobertura.** Cuántos activos tienen el dato, sobre el total. Es lo primero
que hay que mirar y la trampa más cara del sistema: un activo sin dato **no se
castiga**, se saltea y su peso se reparte entre las demás señales, así que
**sube en el ranking por no tener el dato**. Si el indicador no cubre a todos,
pedilo también en el filtro de elegibilidad de la estrategia, donde el faltante
sí deja afuera.

**Saturación.** Qué porcentaje quedaría recortado por la escala, y de qué lado.
Un buen punto de partida es ~10% en total, repartido parejo. Ojo con mirar solo
el total: 15% abajo y 2% arriba suma 17% pero está diciendo que la escala está
corrida.

**Puntajes distintos.** Cuántos valores diferentes produce la señal. Una señal
por tramos con cinco escalones parte el universo en cinco bloques, y adentro de
cada bloque no ordena nada — algo que ni la saturación ni los percentiles
muestran.

**Por grupo.** Abrir la distribución por tipo de instrumento o por sector
responde una pregunta que el número global esconde: el rango diario típico de
una cripto y el de una empresa de servicios públicos no viven en la misma
escala, así que un corte único puede estar bien para una e inservible para la
otra.

## Después de cambiar una escala

**Cambiar los parámetros de una señal no recalcula lo ya guardado.** La
historia sigue con la definición anterior hasta que corras un recálculo
completo desde el [Centro de Datos](/manual/centro-de-datos) — y hasta
entonces, un [backtest](/manual/backtest) estaría midiendo la versión vieja.

Si vas a cambiar varias señales, hacelo todo junto y recalculá una sola vez:
sale más barato que hacerlo de a una.
