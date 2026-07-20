---
slug: carteras
title: Carteras
chapter: 4. Backtest y Carteras
order: 460
roles: analista
page: /carteras
---

Una **biblioteca de carteras**, en el mismo sentido en que hay una biblioteca de
activos o de estrategias: podés tener todas las que quieras, cada una con su dueño
y su visibilidad. Se llega desde **Configuración → Carteras**. Hay dos tipos, y la
diferencia cambia de dónde sale la composición y qué se puede calcular con ella.

| | **Real** | **Seguimiento (teórica)** |
|---|---|---|
| De dónde sale su contenido | Del **registro de operaciones** que cargás vos (plata real) | De una definición: lista curada o top-N de una estrategia |
| Qué se deriva | Posiciones, precio promedio, P&L realizado y no realizado | Pesos objetivo y, en las curadas, curva de rendimiento |
| Para qué sirve | Llevar y valuar tu operatoria | Seguir una idea sin operarla, y servir de objetivo |

La regla práctica: si querés **medir una idea**, hacé una de seguimiento; si querés
**saber cómo venís**, hacé una real; si querés las dos cosas —que es lo interesante—
hacé una de cada una y **vinculalas** (última sección).

## La lista

Arriba están el filtro **Todas / Seguimiento / Reales** y el botón **+ Nueva
cartera**. La tabla muestra **Nombre**, **Tipo**, **Dueño**, **Pública** y
**Moneda**, y se ordena y filtra por cualquier columna. Al seleccionar una cartera
con la tilde de su fila se habilitan **Editar** y **Eliminar** —solo si la podés
editar— y se despliega su **detalle** debajo, donde está todo el contenido real de
la pantalla.

Tienen **dueño y visibilidad** igual que las señales y las estrategias, con las
mismas reglas ([Visibilidad y permisos](/manual/visibilidad-y-permisos)), y nacen
**privadas**.

## Crear una cartera

El orden importa, porque algunas decisiones no se pueden cambiar después:

1. **+ Nueva cartera** y poné el **Nombre**.
2. Elegí el **Tipo** —**Real** o **Seguimiento (teórica)**—: decide qué campos del
   resto del formulario se usan.
3. **Moneda base** (en la que querés verla valuada) y visibilidad con **Pública
   (visible para todos los usuarios)**.
4. Si es de **Seguimiento**, elegí el **Método**: **Curada (lista manual)** —y
   cargá los papeles en **Activos**— o **Derivada de estrategia** —con su
   **Estrategia** y su **Top-N**—.
5. Si es **Real**, podés elegir una **Teórica objetivo (opcional)**.

> **La composición y el vínculo se definen al crear.** Al **Editar** podés cambiar
> nombre, tipo, moneda y visibilidad, pero no el método de composición, la lista de
> activos, la estrategia ni la teórica vinculada: para eso hay que borrar la cartera
> y crearla de nuevo. Y **Eliminar** no pide confirmación — se lleva también el
> registro de operaciones.

## Carteras reales: el registro de operaciones

Una cartera real **no guarda posiciones**: guarda operaciones, y la posición se
**deriva** de ellas. Eso permite varios lotes del mismo papel, ventas parciales y un
precio promedio que siempre cierra con lo cargado. Para registrar una, seleccioná la
cartera y usá **+ Agregar operación**.

| Campo | Qué poner |
|---|---|
| **Activo** | El papel operado. |
| **Operación** | **Compra**, **Venta**, **Dividendo** o **Split**. |
| **Fecha** | La fecha de la operación. |
| **Cantidad** | Nominales operados. |
| **Precio** | Precio por unidad. **Si lo dejás vacío se toma el cierre de mercado de esa fecha.** |
| **Comisión** | Comisión del intermediario. |
| **Impuestos** | Impuestos ligados a la operación (IVA sobre la comisión, derechos de mercado). |
| **Moneda** | Moneda de la operación. |
| **Nota** | Texto libre para acordarte por qué la hiciste. |

> Dejar el **Precio** vacío es cómodo pero no es gratis: si esa fecha no tiene
> precio (un feriado, un papel que no cotizó), se usa el **último cierre anterior**.
> **Dividendo** y **Split** quedan asentados pero **todavía no se procesan** en el
> cálculo de la posición ni del P&L: no los uses para cuadrar rendimientos. Y las
> operaciones **no se editan ni se borran** — si cargaste una mal, la salida
> disponible hoy es asentar la operación contraria.

### Cómo se calcula el rendimiento

- **Cada compra** suma al costo de la posición la cantidad por el precio **más la
  comisión y los impuestos**; el **precio promedio** es ese costo dividido por la
  cantidad, así que los costos ya están adentro del promedio.
- **Cada venta** realiza ganancia: cantidad × (precio de venta − precio promedio),
  **neto de comisiones e impuestos de esa venta**. El promedio de lo que queda **no
  cambia**; solo baja la cantidad, y al cerrar la posición se limpia (si volvés a
  comprar, arranca uno nuevo).
- **P&L no realizado** = cantidad × (precio de mercado − precio promedio); **P&L
  total** = realizado + no realizado, incluido el de las posiciones ya cerradas.

> Cargá siempre la **compra antes que la venta**: una venta sin posición previa se
> toma contra un promedio de cero y ensucia el P&L realizado. Y la **moneda de la
> operación** queda registrada, pero la conversión automática a la moneda base
> todavía no está y los importes se suman tal cual: por ahora, una cartera, una moneda.

El detalle muestra cuatro indicadores arriba —**Valor de mercado**, **P&L total**,
**P&L no realizado** y **Posiciones** (cuántas abiertas)—, la tabla de **Posiciones
actuales** y el **Registro de operaciones**, donde las operaciones sin precio
figuran como «mercado». En el medio, la curva **Valor de tenencias**: para cada
rueda desde tu primera operación, cuánto valían a precio de cierre los papeles que
tenías ese día — sube o baja tanto por el mercado como porque compraste o vendiste.

## Carteras de seguimiento (teóricas)

No tienen operaciones ni plata: tienen una **composición**, que la pantalla
resuelve y muestra como **Miembros vigentes** con su peso.

**Curada (lista manual)** — los activos que elegiste, con pesos **iguales para
todos**. Es el tipo para "mi lista de seguimiento" o para congelar una selección y
mirarla en el tiempo. Muestra además su **curva de rendimiento**, calculada como si
rebalancearas todos los días a los pesos objetivo.

**Derivada de estrategia** — los **Top-N** activos por score de una estrategia, en
partes iguales, resueltos a la última fecha con scores. No es una foto: **se
actualiza sola** a medida que el ranking cambia, así que responde "¿qué me estaría
diciendo hoy esta estrategia?". No dibuja su curva acá: para eso corré la estrategia
en [Backtest → Cartera](/manual/backtest-cartera), donde además **Promover a
seguimiento** crea la derivada con el top-N que estabas probando.

| Métrica | Qué dice |
|---|---|
| **Retorno total** | Cuánto multiplicó su valor en el período (×2.41 = se multiplicó por 2,41). |
| **CAGR** | El mismo retorno como tasa anual compuesta: lo que hay que mirar para comparar períodos de distinta duración. |
| **Sharpe** | Retorno por unidad de riesgo, anualizado. La de Sharpe más alto llegó al mismo lado con menos sobresaltos. |
| **Máx drawdown** | La peor caída desde un máximo hasta el piso posterior: "¿cuánto tuve que aguantar en el peor momento?". Suele ser la que decide si una cartera es sostenible. |

Cuando una métrica no se puede calcular se muestra un guión, nunca un número
inventado.

## Vincular una real con una teórica

Acá los dos tipos se juntan y la pantalla contesta lo que ninguna cartera sola
responde: **¿lo que hiciste se parece a lo que tu estrategia decía que hicieras?** Si
al crear la real elegiste una **Teórica objetivo**, su detalle suma el bloque
**Desvío vs teórica objetivo**, con una fila por activo:

- **Objetivo** — el peso que ese papel debería tener según la teórica.
- **Real** — el peso que tiene, sobre el valor de mercado de tus posiciones.
- **Desvío** — la diferencia (real − objetivo). **Negativo, en rojo, es un faltante**:
  la estrategia lo pide y no lo tenés, o tenés menos. Positivo, en verde, es un exceso.

Aparecen los activos de los dos lados —lo que tenés y la teórica no pide, y lo que
pide y no tenés—, así que leída de arriba a abajo es la **lista de ajustes
pendientes**. El uso típico son dos pasos: creás la teórica derivada de la
estrategia que querés seguir —o la promovés desde el
[backtest](/manual/backtest)— y después creás la real apuntando a ella.

> Lo que se compara es la **composición de hoy**, no el rendimiento acumulado de
> una contra otra: es una foto de la desviación actual, y se mueve sola cuando la
> teórica es derivada de una estrategia y su ranking cambia.
