---
slug: drawdowns
title: Drawdowns — configuración
chapter: 7. Configuración
order: 760
roles: admin
page: /admin/drawdown-config
---

Un **drawdown** es una caída del precio medida desde el máximo previo. La
pantalla no dibuja drawdowns nuevos: define **cuál de todas las bajadas merece
llamarse una caída** y quedar registrada como un evento con nombre propio.

La distinción importa porque un activo baja todos los días un poco. Sin un
criterio de corte, la historia de cualquier acción tendría miles de "caídas" de
2%. Lo que configurás acá es el filtro que separa el ruido de las crisis.

Es una pantalla solo para **administradores**, y la configuración es **única
para todo el sistema**: el mismo criterio se aplica a todos los activos.

---

## Cómo detecta el sistema una caída

El mecanismo tiene tres momentos y conviene tenerlos claros porque explican casi
todo lo que después sorprende en el gráfico:

1. **Arranque.** El sistema recorre la serie de **cierres** y va llevando el
   máximo alcanzado hasta ese día. En cuanto un cierre queda por debajo de ese
   máximo, empieza a seguir una posible caída.
2. **Piso.** Mientras el precio siga por debajo del máximo, se va quedando con
   el cierre más bajo alcanzado. Ese es el **piso** de la caída.
3. **Recuperación.** La caída se da por **terminada solo cuando el precio vuelve
   a superar el máximo anterior**. Recién ahí se mide la profundidad (del máximo
   al piso) y se decide si el episodio se registra o se descarta.

Es decir: la recuperación **no es un parámetro que puedas ajustar**, es la regla
fija que cierra el evento. Y es una recuperación **total** — volver al máximo
previo, no "rebotar un poco".

---

## El parámetro

| Campo | Qué controla |
|---|---|
| **Profundidad mínima (%)** | Cuánto tiene que haber caído el precio desde el máximo previo, hasta su piso, para que el episodio se registre como drawdown. Las caídas menores se descartan por completo. |

Se carga como porcentaje positivo, admite decimales de a medio punto y acepta
valores de 1 a 90. Si nunca lo tocaste, el sistema trabaja con **20%**.

La pantalla sugiere puntos de partida según el tipo de activo: **20–30%** para
acciones individuales, **10–15%** para índices, **40–50%** para cripto. Un valor
bajo llena el gráfico de marcas; uno alto deja solo las crisis grandes.

Para guardar, **Guardar**. La pantalla confirma el guardado y te recuerda
recalcular los indicadores.

> **El umbral es uno solo para todos los activos.** Los valores sugeridos
> difieren mucho entre acciones, índices y cripto, pero no hay forma de fijar un
> umbral por activo ni por grupo. Si tu universo es mixto, elegí pensando en el
> tipo de activo que más te importa analizar: con 40% los índices no van a
> mostrar casi ninguna caída, y con 10% una cripto va a mostrar decenas.

---

## Las tres sutilezas que más confunden

### No hay caídas anidadas

Como una caída solo termina cuando el precio recupera el máximo anterior, **dos
derrumbes separados por un rebote incompleto son un solo evento**. Si un activo
cae 25%, rebota hasta quedar 3% abajo del máximo y después se desploma hasta
−45%, no vas a ver dos marcas: vas a ver **una sola de −45%**, cuyo inicio es el
primer día de la primera bajada. Por eso algunos eventos abarcan períodos
larguísimos, y por eso la profundidad que se muestra es siempre la del punto más
bajo de todo el episodio.

### Se mide sobre cierres, no sobre mínimos intradiarios

Toda la detección usa el **precio de cierre**. Una caída que en el intradiario
llegó a −22% pero nunca cerró peor que −19,8% **no supera un umbral de 20%** y
no aparece. Si te llama la atención que falte una caída que recordás como
importante, esta suele ser la razón.

### El "máximo histórico" es el de la historia cargada

El punto de referencia es el máximo dentro de la serie de precios que el sistema
tiene para ese activo, no el máximo de toda la vida del papel. En un activo con
pocos años cargados, el primer cierre disponible funciona como máximo inicial.
Si extendés la historia hacia atrás, las caídas detectadas pueden cambiar.

---

## Dónde se ven los drawdowns

En [Análisis de Activo](/manual/analisis-de-activo), solapa «Gráfico Técnico»,
hay dos cosas distintas que conviene no mezclar:

| Control | Qué muestra | ¿Depende del umbral? |
|---|---|---|
| **Drawdown Pisos** | Triángulos rojos sobre el precio, en el piso de cada caída detectada, con su profundidad %. | **Sí.** Son los eventos que pasaron el filtro. |
| **Drawdown %** | Un panel debajo del precio con la caída % desde el máximo previo, día a día. | **No.** Es una línea continua, sin filtro de ningún tipo. |

En el [Screener de Señales](/manual/screener-de-senales) están disponibles la
profundidad del **drawdown actual** y las **tres peores lecturas históricas** del
activo, que también se pueden usar como insumo de una señal por umbrales
(por ejemplo: mejor que −5% → 100, mejor que −15% → 50, peor que −30% → −50).

> **Las "tres peores" no son tres caídas distintas.** Son las tres lecturas
> diarias más profundas de toda la serie. Como los días alrededor de un piso
> tienen profundidades casi idénticas, lo habitual es que las tres pertenezcan
> **al mismo derrumbe**. No las leas como "las tres crisis más grandes del
> activo"; para eso mirá las marcas del gráfico.

---

## Después de cambiar el umbral

Las marcas de **Drawdown Pisos** se calculan en el momento de dibujar el
gráfico, así que el nuevo umbral se refleja apenas vuelvas a abrir el activo.

Los valores del screener (drawdown actual y las tres peores lecturas) son
**pre-calculados** y se refrescan con el pipeline de indicadores, igual que el
resto: revisá [cómo se calcula todo](/manual/conceptos-pipeline) si no tenés
presente la diferencia entre actualización incremental y recálculo completo.
Cambiar este parámetro **no borra ni destruye nada** — no hay historia de
drawdowns que se pierda, la detección se rehace entera cada vez.
