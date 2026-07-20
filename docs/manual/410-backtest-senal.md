---
slug: backtest-senal
title: Nivel Señal — calidad del ranking
chapter: 4. Backtest y Carteras
order: 410
roles: invitado
---

Es la primera solapa del [Backtest](/manual/backtest) y la que hay que correr
antes que ninguna otra. Responde la pregunta más básica: **¿el ranking de la
estrategia sirve para ordenar activos?** Los que pone arriba, ¿rinden después
más que los que pone abajo? No simula ni una operación —no hay compras, ni
stops, ni costos—: mide la **materia prima**. Si el score no ordena nada, no hay
juego de reglas ni tamaño de cartera que lo salve.

---

## Cómo mide

En cada fecha toma los activos elegibles, los **ordena por score** y los parte
en cuantiles: con 10 cuantiles, el cuantil 10 es el décimo de mejor score y el 1
el de peor. Después mide cuánto rindió cada cuantil en las ruedas siguientes, y
repite eso fecha por fecha. Tres detalles cambian cómo se leen los números:

- **No hay futuro en la señal.** El score se conoce al cierre del día, la
  posición se toma al cierre de la rueda **siguiente** y recién ahí arranca el
  retorno.
- **Los horizontes son ruedas propias del activo**, no días de calendario:
  horizonte 20 significa "20 ruedas en las que ese activo cotizó".
- **Cada fecha pesa lo mismo**: el retorno de un cuantil en una fecha es el
  promedio simple de sus activos, y el número final promedia esas fechas — un
  día con 25 activos pesa igual que uno con 500.

### Solo se miran fechas en que el activo cotizó

Parece un detalle técnico y es lo que más cambia los resultados. El sistema
arrastra el último score conocido a los días en que un activo **no** cotizó
(feriado local, suspensión, baja de cotización): sirve para mirar una pantalla,
pero es veneno para medir, porque se estaría midiendo una posición tomada un día
sin precio. El backtest los **descarta**: un activo entra a una fecha solo si
cotizó ese día exacto. Por eso puede haber bastante menos activos por fecha que
en el ranking que ves en pantalla.

---

## Los controles

| Control | Para qué sirve |
|---|---|
| **Estrategia** | La estrategia a evaluar. Aparecen las públicas y las tuyas (si sos admin, todas). |
| **Horizontes (ruedas)** | Cuántas ruedas hacia adelante se mide el retorno. Podés elegir varios a la vez (1, 5, 10, 20, 60, 120, 250); vienen 1, 5, 20 y 60. Cada uno se calcula por separado y aparece como serie propia en los gráficos. |
| **Cuantiles** | En cuántos grupos se parte cada fecha (2 a 20; por defecto 10, o sea deciles). Menos cuantiles = grupos más grandes y estables; más = extremos más finos pero más ruidosos. |
| **Mín. activos** | Cuántos activos válidos necesita una fecha para contar. Si no llega, se saltea. Nunca puede ser menor que la cantidad de cuantiles: el sistema lo sube solo. |
| **Desde (opcional)** | Recorta el período. Vacío = toda la historia calculada. |
| **Ejecutar backtest** | Lanza la corrida en segundo plano, con barra de progreso. |
| **Corridas guardadas** | Las corridas ya hechas sobre estrategias que podés ver. Elegir una muestra sus resultados. |

Cada corrida se guarda **sola**, con su configuración: en la lista figura por
número, estrategia, fecha y hora, horizontes, cuantiles y fechas calculadas. Las
que fallaron aparecen marcadas, pero no se pueden abrir.

> Si termina diciendo que **la estrategia no tiene historia calculada en el
> período**, falta un recálculo completo de señales y estrategias. Si avisa que
> **ninguna fecha alcanzó el mínimo de observaciones**, el universo es chico para
> lo que pediste: bajá **Mín. activos** o revisá el filtro de elegibilidad.

---

## Cómo se leen los resultados

Arriba, el resumen de la corrida: número, período, fechas y configuración.

### Las tarjetas de IC, una por horizonte

Muestran el **IC medio**, su **t** entre paréntesis y en qué porcentaje de las
fechas el IC dio positivo. El **IC** es, en castellano llano, **una nota a la
capacidad de ordenar**: en cada fecha compara el orden en que la estrategia puso
a los activos con el orden en que después rindieron. **1** es orden perfecto,
**0** es que un orden y el otro no tienen que ver, y **negativo** significa que
ordenó al revés — sus mejores rindieron peor que sus peores.

Lo que ves es el **promedio** de esos valores diarios, y no esperes números
grandes: sobre un universo entero, un IC chico pero **sostenido** vale mucho más
que uno grande que aparece dos meses y se da vuelta. Por eso el **porcentaje de
fechas con IC positivo** suele ser más informativo que el promedio: dice si la
ventaja fue persistente o si vino de un puñado de días excepcionales. La **t**
mide aproximadamente cuánto se distingue ese promedio del puro ruido; es un
indicio, no un veredicto. **IC no computable** significa que no hubo
observaciones suficientes en ese horizonte.

### Retorno medio por cuantil

El gráfico de barras, con una barra por horizonte. **El cuantil más alto es el
de mejor score.** Lo que hay que buscar no es que la última barra sea grande,
sino que las barras formen una **escalera**: una progresión ordenada dice que el
score discrimina en todo su recorrido. Si es plano en el medio y solo se levantan
los extremos, separa lo muy bueno de lo muy malo pero no dice nada del resto.

> **Ese retorno es el de un período de la longitud del horizonte, no un
> acumulado ni un rendimiento anual.** En el horizonte 20 la barra dice cuánto
> rindió ese cuantil **cada 20 ruedas**: comparar horizontes entre sí no tiene
> sentido, son unidades diferentes.

### IC en el tiempo y spread en el tiempo

Las dos series de abajo son medias móviles de 60 fechas, para ver tendencia y no
ruido diario. La primera muestra si la ventaja fue estable o si se concentró en
un tramo. La segunda es el **spread**: cuánto rindió el cuantil de mejor score
por encima del de peor, fecha por fecha. Un spread que cruza el cero seguido
significa que en muchos períodos los peores rindieron más que los mejores.

---

## Qué se puede concluir y qué no

**Sí**, si el IC medio es positivo, persiste y las barras arman escalera: en ese
período y ese universo el score **ordenó** los activos en el sentido esperado.
Eso habilita a pasar a [Reglas](/manual/backtest-reglas) y
[Cartera](/manual/backtest-cartera).

**No se puede concluir que esto es lo que vas a ganar.** Ninguno de estos
números es el resultado de una estrategia operable:

- No hay **costos** ni comisiones, y cada cuantil se trata como una cartera que
  se rearma **todos los días con todos sus activos en partes iguales**, sin
  límite de posiciones ni de capital.
- No hay reglas de **salida**: la solapa no dice cuándo entrar ni cuándo salir,
  solo que el orden tenía información.
- Un spread positivo puede venir enteramente de que **el cuantil peor cayó
  mucho**; si solo comprás, esa mitad de la ventaja no la capturás. Mirá el
  cuantil superior contra el promedio, no solo la diferencia entre extremos.
- Es **un** período y **un** universo: un backtest bueno no es una promesa, es
  la ausencia de una mala noticia.

> **Si la estrategia produce muchos scores idénticos** —típico cuando viene de
> señales con pocas categorías—, el corte entre cuantiles vecinos cae en el medio
> de un montón de empates y es arbitrario: conviene bajar la cantidad de
> cuantiles, porque las diferencias entre grupos contiguos no significan nada.

Por último: una corrida es una **foto**, se guarda como salió y nunca se
recalcula. Si cambiás la estrategia, sigue mostrando los números viejos — que es
lo que la hace útil para comparar.
