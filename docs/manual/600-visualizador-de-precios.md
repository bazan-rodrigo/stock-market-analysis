---
slug: visualizador-de-precios
title: Visualizador de precios
chapter: 6. Datos de Mercado
order: 600
roles: invitado
page: /price-viewer
---

Es la vista más cruda del sistema: los precios tal como quedaron guardados,
**sin ningún cálculo encima**. No hay indicadores, ni señales, ni scores — solo
apertura, máximo, mínimo, cierre y volumen.

Suena poco, pero es la pantalla a la que hay que venir cada vez que algo *más
arriba* en la cadena se ve raro. Si un indicador da un valor imposible o un
activo desapareció del ranking, la primera pregunta siempre es la misma:
**¿el precio está bien?** Acá se responde en diez segundos, y se evita perder
media hora buscando el problema en el lugar equivocado.

Arriba de todo elegís entre los dos modos de consulta.

---

## Modo «Último precio de todos los instrumentos»

Es el que aparece al entrar. Una fila por activo, con su **cotización más
reciente** y sus datos de referencia:

| Columna | Qué muestra |
|---|---|
| **Ticker** / **Nombre** | Identificación del activo. |
| **Fecha** | El día al que corresponde ese precio. La columna más importante de la pantalla. |
| **Apertura** / **Máx** / **Mín** / **Cierre** | La cotización de ese día. |
| **Volumen** | Cantidad operada. |
| **Moneda**, **Tipo**, **País**, **Mercado** | Los grupos a los que pertenece el activo (ver [Activos y grupos](/manual/activos-y-grupos)). |
| **Fuente** | De dónde sale el precio: la fuente externa, o *Calculado* si es un sintético o una conversión de moneda. |

Arriba de la tabla se indica cuántos instrumentos tienen precio disponible. Los
activos **sin ningún precio descargado no aparecen acá** — si buscás uno y no
está, ese es el dato: nunca se le bajó la serie.

### Para qué se usa realmente

**Para detectar activos atrasados.** Ordená por **Fecha** de menor a mayor: los
que quedaron arriba son los que hace más tiempo que no se actualizan. Algunas
diferencias son legítimas (mercados distintos, feriados locales, activos que
dejaron de cotizar), pero un activo que quedó semanas atrás de todos sus pares
casi siempre indica una descarga que viene fallando.

**Para verificar un sintético.** Después de crear un activo calculado o una
conversión de moneda, este es el lugar donde se confirma que efectivamente se
está calculando y con qué fecha llega.

**Para confirmar una cotización sospechosa.** Si un indicador quedó en un valor
absurdo, mirá el cierre acá antes que nada: un precio mal descargado explica
más problemas que cualquier error de cálculo.

---

## Modo «Historia de un instrumento»

Elegís un activo en el selector y la tabla muestra **toda su serie diaria**, de
la fecha más vieja a la más nueva, con las mismas columnas de precio y volumen.

Debajo del selector se indica cuántos registros hay y entre qué fechas van, que
es la forma más rápida de responder "¿desde cuándo tengo historia de este
activo?" — dato clave antes de meterlo en un backtest, porque un activo con
poca historia arrastra conclusiones frágiles.

Si el activo no tiene precios descargados, la pantalla lo avisa explícitamente
en vez de mostrar una tabla vacía sin explicación.

---

## Cómo moverse en las tablas

Las dos tablas funcionan igual:

- **Ordenar**: clic en el título de la columna.
- **Filtrar**: la fila de filtros debajo de los títulos permite acotar por
  cualquier columna. En el modo «último precio» es lo que te deja quedarte solo
  con un mercado, una moneda o un tipo de instrumento.
- **Paginado**: 50 filas por página.

---

## Cosas a tener en cuenta

> **Esta pantalla no descarga ni modifica nada.** Es solo de lectura: muestra
> lo que ya está guardado. Para forzar una descarga hay que ir a
> [Actualización de precios](/manual/actualizacion-de-precios), que es de
> administrador.

> **El último día puede cambiar.** Mientras el mercado no cerró, la cotización
> del día en curso es provisoria y se reescribe en la siguiente actualización.
> No es un error: está explicado en
> [Cómo se calcula todo](/manual/conceptos-pipeline).

Un detalle que conviene tener presente: acá ves el precio **crudo**, mientras
que el gráfico de [Análisis de Activo](/manual/analisis-de-activo) puede
mostrarlo agrupado por semana o por mes según la frecuencia que hayas elegido.
Si los números no coinciden, revisá primero esa configuración antes de suponer
que hay una inconsistencia en los datos.
