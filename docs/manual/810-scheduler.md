---
slug: scheduler
title: Scheduler
chapter: 8. Administración
order: 810
roles: admin
page: /admin/scheduler
---

El **Scheduler** es el reloj del sistema: lo que hace que los datos se
actualicen solos, todas las noches, sin que nadie apriete nada. Se llega desde
**Administración → Scheduler** y solo lo ven los administradores. Tiene dos
bloques independientes, cada uno con su estado, sus controles y su horario:
**Scheduler de precios** (la corrida diaria) y **Verificación semanal de
datos**.

> **Todos los horarios de esta pantalla están en UTC**, no en hora local. Para
> hora de Argentina hay que restar 3 horas: 18:00 UTC son las 15:00 acá.

---

## La corrida diaria

Cuando llega la hora configurada, el sistema ejecuta en cadena: **precios** de
todos los activos (incluidos sintéticos y conversiones de moneda) → **indicadores
técnicos** → **fundamentales** de los activos con fuente configurada y sus
ratios → **agregados de tendencia por grupo** → **señales y estrategias**. Todo
en modo incremental: calcula las fechas que tienen precio pero no cálculo, y
**siempre recalcula la última**.

Es exactamente lo mismo que se dispara a mano desde el
[Centro de Datos](/manual/centro-de-datos), en el mismo orden. Por eso en el día
a día no hace falta entrar a ninguna pantalla de administración.

Un detalle que tranquiliza: si la aplicación estuvo apagada unos días, **no hay
que hacer nada especial**. La primera corrida que agarre prendida la app
completa sola los días faltantes.

> **Lo que la corrida diaria NO hace: incorporar activos nuevos a la historia
> pasada de señales y rankings.** Como el ranking es transversal, eso exige un
> **recálculo completo** desde el Centro de Datos. Ver
> [el pipeline](/manual/conceptos-pipeline).

### Estado y controles

| Elemento | Qué muestra o hace |
|---|---|
| **Estado** | *Activo* (el reloj corre) o *Detenido*. |
| **Próxima ejecución** | Fecha y hora exactas del próximo disparo, en UTC. Es la mejor confirmación de que el horario quedó aplicado. |
| **Horario configurado** | El horario guardado, aunque el scheduler esté detenido. |
| **Iniciar** / **Detener** | Prende y apaga el reloj. |
| **Ejecutar ahora** | Adelanta la corrida a este mismo momento. No cambia el horario: la próxima ejecución vuelve a su hora normal. |
| **Hora** / **Minuto** + **Aplicar** | Cambia el horario diario (0–23 y 0–59). |

**"Ejecutar ahora" solo funciona con el scheduler activo.** Si está detenido, la
pantalla avisa que no está corriendo: hay que **Iniciar** primero, o usar el
Centro de Datos, que sí funciona con el reloj apagado.

### Si el scheduler está detenido, los datos dejan de actualizarse

Vale la pena decirlo con todas las letras: en *Detenido* **no se descarga ni se
calcula nada automáticamente**. Los precios quedan en la última fecha bajada,
las señales y los rankings congelados, y las pantallas de análisis siguen
mostrando datos viejos sin ningún cartel de advertencia. La única pista es la
fecha del último dato.

Además, **el estado sobrevive a los reinicios**: si lo dejás detenido y el
servidor se reinicia, arranca detenido; si lo dejaste activo, vuelve solo.
Detenerlo es una decisión que hay que acordarse de revertir.

### Cambiar el horario sin sorpresas

La pantalla se refresca sola cada diez segundos y en cada refresco **vuelve a
escribir en Hora y Minuto el horario guardado**. Si tipeás un valor nuevo y te
distraés, el campo vuelve al anterior y el cambio se pierde: escribí y apretá
**Aplicar** sin demorarte.

Segunda sutileza, en el mismo lugar: **después de haber usado Aplicar una vez en
esa visita, los cambios de hora o minuto se toman apenas los escribís**, sin
volver a apretar el botón. Como se toma cada tecla, escribir "23" puede guardar
primero las 2 y después las 23. No es grave —queda el último valor tipeado—,
pero por eso la regla práctica es siempre la misma: escribí el horario completo
y **confirmalo leyendo Horario configurado y Próxima ejecución**, que es lo que
de verdad está guardado. El horario se puede cambiar con el scheduler detenido:
queda guardado y rige cuando lo prendas.

### Qué hora conviene elegir, y cuándo la corrida se saltea

Poné la corrida **después del cierre de los mercados que seguís**. Si corre con
las ruedas abiertas, el precio del día entra a mitad de sesión: no es un error,
porque [el último día siempre es preliminar](/manual/conceptos-pipeline) y la
corrida siguiente lo recalcula, pero conviene saberlo antes de mirar el ranking
de la mañana.

Si en el momento del disparo hay **otra operación pesada en curso** (un
recálculo lanzado a mano desde el Centro de Datos, por ejemplo), la corrida
diaria **se saltea** en lugar de escribir en paralelo sobre las mismas tablas.
No se reintenta más tarde: se retoma al día siguiente y, por ser incremental,
recupera lo que faltó. Por eso conviene lanzar los recálculos largos lejos del
horario nocturno. Hay además una tolerancia de **una hora** para arranques
demorados; pasada esa hora se saltea el día. Y nunca corren dos a la vez: si la
corrida anterior sigue viva cuando llega el próximo disparo, el nuevo no se
lanza.

### Si la corrida falla a mitad de la cadena

La cadena tiene dos tramos, y fallan distinto:

- **Un activo que falla no corta nada.** La corrida sigue con los demás y el
  activo queda con su error anotado, ficha por ficha, en
  [Actualización de precios](/manual/actualizacion-de-precios) o en
  [Actualización de fundamentales](/manual/actualizacion-de-fundamentales),
  donde está el botón **Reintentar fallidos**.
- **Si el tramo de datos** (precios → indicadores → fundamentales) **muere
  entero**, la corrida termina ahí: esa noche las señales y el ranking ni se
  intentan.
- **Si el tramo de señales y estrategias falla**, los precios e indicadores del
  día ya quedaron guardados, pero el ranking queda en la fecha anterior.

En los dos últimos casos el síntoma visible es el mismo y es engañoso: **las
pantallas muestran precios de hoy con un ranking de ayer**, sin ningún cartel.
No hay reintento esa misma noche, pero tampoco hace falta intervenir: la
corrida siguiente, por ser incremental, detecta las fechas que tienen precio y
no tienen señales y las completa. Si no querés esperar, el botón **Ejecutar**
de Señales y Estrategias en el [Centro de Datos](/manual/centro-de-datos) hace
exactamente eso a mano.

> **No hay una vista única de "qué pasó anoche".** Se reconstruye con tres
> piezas: el registro por activo de
> [Actualización de precios](/manual/actualizacion-de-precios) y de
> [fundamentales](/manual/actualizacion-de-fundamentales), y el mensaje de
> última corrida de cada tarjeta del
> [Centro de Datos](/manual/centro-de-datos), que guarda inicio, fin y duración
> por etapa.

---

## Verificación semanal de datos

Es un **control de calidad**, no una actualización. Recalcula desde cero, en
memoria, todos los indicadores y ratios fundamentales de **todos** los activos y
los compara contra lo guardado. Donde hay diferencias marca el activo,
distinguiendo **discrepancias de cálculo** (lo guardado no coincide con lo
recalculado) de **posibles errores de datos de origen**.

El resultado son los **⚠️** que aparecen delante del código del activo en los
selectores de [Análisis de Activo](/manual/analisis-de-activo),
[Rotación Relativa](/manual/rotacion-relativa), [Evolución](/manual/evolucion),
[Análisis de Pares](/manual/analisis-de-pares) y
[Comparador de Retornos](/manual/comparador-de-retornos). La marca solo avisa
que ese activo tiene hallazgos; para ver el detalle —cuántas discrepancias de
cálculo y cuántos posibles errores de origen— hay que entrar a
[Verificación de datos](/manual/verificacion-de-datos).

> **La verificación marca, no repara.** No corrige ni reescribe ningún dato: un
> activo marcado se arregla desde el Centro de Datos, típicamente con un
> recálculo completo.

Se maneja igual que la corrida diaria, con **Día**, **Hora** y **Minuto** más
**Aplicar**, y con **Habilitar**, **Deshabilitar** y **Ejecutar ahora**. Valen
las mismas dos sutilezas de los campos de horario descriptas más arriba.

### Es independiente, y nace apagada

Tiene **su propio interruptor** y viene deshabilitada de fábrica: prender el
scheduler de precios no la prende. Pero sí **necesita** el reloj de arriba
prendido para correr, porque lo comparten. De ahí los tres estados posibles:

| Estado | Qué significa |
|---|---|
| **Activo** | Habilitada y corriendo: se ejecuta en la fecha indicada. |
| **Habilitado (scheduler detenido)** | Habilitada, pero el reloj de arriba está apagado y por lo tanto **no va a correr**. Hay que apretar **Iniciar** en el bloque de precios. |
| **Deshabilitado** | Apagada. Los ⚠️ existentes quedan como están, sin actualizarse. |

Una corrida completa recorre todo el universo y **tarda lo mismo que un
recálculo completo de indicadores**: es una operación larga y exigente. A
diferencia de la corrida diaria, **no se saltea si encuentra el sistema
ocupado**. Programala en una franja tranquila y **lejos del horario de la
actualización diaria** y de los recálculos manuales — un fin de semana de
madrugada es buena elección. **Ejecutar ahora** solo funciona si la verificación
está habilitada y el scheduler corriendo; si no, la pantalla avisa y no dispara
nada.

---

## Rutina sugerida

Dejá el scheduler **Activo** de forma permanente, con la corrida diaria después
del cierre, y la verificación semanal habilitada en una franja de baja
actividad. Si lo detuviste para hacer mantenimiento, **acordate de volver a
iniciarlo**: nada te lo va a recordar.
