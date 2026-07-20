---
slug: correlacion-de-precios
title: Correlación de Precios
chapter: 3. Análisis
order: 365
roles: invitado
page: /scatter
---

Se llega desde **Análisis → Correlación de Precios**.

Enfrenta **dos activos en un gráfico de dispersión**: cada punto es un día, con
el precio de cierre del primer activo en el eje horizontal y el del segundo en
el vertical. La nube que se forma muestra de un vistazo si los dos se mueven
juntos, si se mueven en sentidos opuestos o si no tienen nada que ver.

Es la herramienta para preguntas de relación entre pares: ¿esta acción sigue a
su índice?, ¿el ratio entre estas dos se mantuvo estable?, ¿desde cuándo se
despegaron?

---

## Elegir los dos activos

| Control | Para qué sirve |
|---|---|
| **Activo 1 (eje X)** | El activo horizontal. Suele convenir poner acá el "explicativo" (el índice, la materia prima, el dólar). |
| **⇄** | Intercambia los dos activos de eje. |
| **Activo 2 (eje Y)** | El activo vertical, el que se lee como "explicado". |
| **Eventos de mercado** | Resalta los períodos de eventos cargados en el sistema (ver más abajo). |

El gráfico se arma con **todos los días en que ambos activos tienen precio**.
No hay selector de fechas: se usa la historia común completa, y el pie del
gráfico informa desde cuándo hasta cuándo va. Si los dos activos no comparten
ninguna fecha, aparece el aviso correspondiente y no se dibuja nada; lo mismo si
elegís dos veces el mismo activo.

El orden importa menos de lo que parece: el botón **⇄** no cambia la
correlación, que es simétrica. Sí cambia la línea de tendencia —también la
lineal—, porque lo que se dibuja es siempre el ajuste de Y sobre X, y ese no
es el mismo que el de X sobre Y; lo único que la simetría deja intacto, además
de la correlación, es el R² del ajuste lineal.

---

## Cómo leer la nube

El color de los puntos codifica **el tiempo**: la escala de la derecha, rotulada
*Tiempo*, va de la fecha más antigua a la más reciente. Esto es lo que convierte
una nube estática en una historia — permite ver que la relación de los últimos
años ocupa una zona distinta del gráfico que la de hace una década, aunque la
nube en conjunto parezca compacta.

El **último día disponible se marca aparte, en rojo y con su fecha escrita al
lado**. Es la referencia de "dónde estamos hoy" dentro de toda esa historia.

Con la rueda del mouse se hace zoom sobre cualquier zona. El zoom es **solo
visual**: la correlación y el ajuste que se informan siguen calculados sobre
todos los puntos, no sobre los que quedan a la vista.

### Eventos de mercado

Al activar **Eventos de mercado** entran los eventos de alcance global y los
específicos de cualquiera de los dos activos elegidos. Se ven de dos maneras:
los puntos cuyos días caen dentro del rango del evento se pintan del color del
evento, y una **estrella con el nombre** marca la posición del día más cercano
al centro del período. Es la forma rápida de contestar "¿esta desviación de la
nube fue la crisis de tal año?".

---

## Línea de tendencia

El ajuste que se dibuja sobre la nube, en amarillo punteado, con la ecuación en
la leyenda y el **R²** destacado arriba a la izquierda. El R² va de 0 a 1 e
indica qué porción del movimiento de un activo queda explicada por el otro bajo
esa forma funcional.

| Tipo | Cuándo tiene sentido |
|---|---|
| **Ninguna** | Por defecto. Para mirar la forma de la nube sin sugestionarse. |
| **Lineal** | La relación de referencia: "sube uno, sube el otro en proporción constante". |
| **Logarítmica** | Cuando el efecto se va agotando: el segundo activo reacciona cada vez menos a subas del primero. |
| **Polinómica** | Relaciones con curvatura o cambio de sentido. El campo **Grado** (de 2 a 10) controla cuánto se dobla la curva. |
| **Exponencial** | Cuando el segundo activo crece a tasa proporcional a su propio nivel. |

> Cuidado con subir el **Grado**: un polinomio de grado alto siempre mejora el
> R² porque tiene más libertad para pasar cerca de los puntos, y eso no
> significa que haya encontrado una relación real. Un grado 8 con R² alto suele
> describir el ruido, no el vínculo entre los activos.

Dos ajustes tienen requisitos y, si no se cumplen, la línea sencillamente no se
dibuja: el **logarítmico** necesita que todos los precios del eje X sean
mayores que cero, y el **exponencial** lo mismo para el eje Y.

El switch **Escala logarítmica — Ambos ejes** cambia cómo se dibujan los ejes,
no cómo se calcula el ajuste. Con la escala prendida, una tendencia lineal se
ve curva: es un efecto de la representación, la recta sigue siendo la misma.
La escala logarítmica es útil cuando alguno de los dos activos recorrió varios
órdenes de magnitud y en escala normal toda la historia vieja se aplasta contra
el origen.

---

## Las estadísticas del pie, y cómo no malinterpretarlas

Debajo del gráfico se informan la cantidad de puntos, el rango de fechas
cubierto y la **correlación de los retornos diarios** entre los dos activos
(solo si hay al menos tres retornos diarios para calcularla, es decir cuatro o
más días en común con precio válido). Va de −1 a +1: +1 es relación positiva
perfecta, −1 inversa perfecta, 0 ninguna relación lineal.

> **La correlación se mide sobre los retornos, no sobre los niveles de precio.**
> Es una distinción que importa: dos activos que simplemente subieron a lo
> largo de los años comparten la tendencia, y si se los correlacionara por
> precio darían casi 1 aunque su comportamiento diario no tenga nada que ver.
> Al calcularla sobre las variaciones diarias, el coeficiente responde la
> pregunta que realmente interesa —"¿se mueven juntos día a día?"— y no la
> engañosa "¿estuvieron caros al mismo tiempo?".
>
> Ojo entonces con la nube: **la nube es de precios** (cada punto es el par de
> cierres de un día), pero **el coeficiente es de retornos**. Miden cosas
> distintas a propósito, y por eso una nube que sube prolija puede venir
> acompañada de una correlación baja.

> **Correlación no es causalidad.** Que dos series se muevan juntas no dice cuál
> mueve a cuál, ni descarta que un tercer factor mueva a las dos. Un R² alto es
> un punto de partida para investigar, nunca una conclusión.

Lo más informativo suele ser lo que rompe el patrón: una nube que se **parte en
dos zonas**, o un tramo reciente de color claro que se aleja de la diagonal que
siguieron todos los años anteriores. Eso es un cambio de régimen en la relación,
y se ve a ojo mucho antes que en cualquier número.
