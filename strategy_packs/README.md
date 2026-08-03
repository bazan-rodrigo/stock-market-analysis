# Strategy packs

Packs listos para importar desde la app.

> **El formato está especificado en [SPEC.md](SPEC.md)** — el contrato que
> permite que cualquiera (una persona, o un modelo de lenguaje sin acceso a
> este repositorio) escriba un pack importable. El formato canónico es **un
> archivo JSON**; las planillas Excel de este directorio son el formato
> histórico y siguen funcionando.
>
> Para escribir uno hacen falta dos cosas: el SPEC y el **catálogo de la
> instalación de destino**, que dice qué indicadores y qué sectores/mercados
> existen ahí. Los dos se bajan de la pantalla **Packs** (`/admin/packs`), que
> es también donde se importa; el botón *Catálogo* está además en la pantalla
> de Señales. Se valida sin base ni app con
> `python scripts/validate_pack.py <pack>.json --catalog catalogo.json`.

Hoy hay **un solo pack publicado**: `senales_base`, el catálogo de señales.
**No hay estrategias** en este directorio — se van a armar más adelante, sobre
estas señales.

El pack está en **los dos formatos**: `senales_base.json` (el canónico) y su
planilla. Se convierten en cualquier dirección, y ninguno de los dos se edita a
mano por separado — se edita uno y se regenera el otro:

```
python scripts/pack_from_json.py strategy_packs/senales_base.json   # JSON  → xlsx
python scripts/pack_to_json.py   strategy_packs/senales_base        # xlsx → JSON
```

`tests/test_pack_spec.py` verifica que los dos formatos digan lo mismo y que el
pack valide sin errores: si quedan desalineados, falla la suite.

## senales_base — una señal por indicador

**Una sola señal por indicador, y todas las que el indicador admite.** El
catálogo cubre **51 de los 57 indicadores** de la instalación: quedan afuera
los seis `best_sma_*` / `best_ema_*`, cuyo valor es el *período* de la media
(una de 200 no es "mejor" que una de 20, así que no hay nada que puntuar).

Antes la regla era la contraria —*toda señal debía estar usada por alguna
estrategia*, para no pagar cómputo de más— y el catálogo crecía pegado a las
estrategias que se iban armando. El costo de eso era peor: aparecían dos y tres
señales sobre el mismo indicador, con umbrales distintos, y dejaba de tener
sentido comparar dos estrategias entre sí (no se sabía si diferían en la idea o
en cómo medía cada una). El catálogo ahora es **independiente de las
estrategias**: se arma completo una vez y las estrategias eligen de ahí.

### La orientación, que es lo que hace comparable al catálogo

**+100 son las mejores condiciones para comprar** —esperando estar largo
mientras el precio sube— y **−100 las peores**. Todas las señales apuntan para
el mismo lado, sin excepción.

Para leer una señal al revés **no se duplica**: un componente de estrategia
admite **peso negativo** (SPEC §5). Así se arma una estrategia bajista, o una
que pida *"momentum alto pero volatilidad baja"*, sin tocar el catálogo.

Los criterios por familia, que es donde la orientación se vuelve una decisión y
no un cálculo:

| Familia | Criterio | Por qué |
|---|---|---|
| Tendencia (diaria/semanal/mensual) | Alcista +100, bajista −100 | Lectura directa del régimen. |
| Volatilidad, ATR %, compresión | Calma +100, extrema −100 | La calma es mejor telón de fondo para estar largo; la duración del régimen modula dentro de cada nivel. |
| ADX | Más fuerza +100 | **No dice dirección**: un derrumbe ordenado también da ADX alto. Va siempre acompañada de tendencia. |
| RSI y distancia en σ a la media óptima | El **retroceso** puntúa +100 | Son medidas de estiramiento: miden el punto de entrada, no la salud. |
| Distancia a medias fijas (20/50/200) | **Por encima** +100 | Son medidas de régimen: miden la salud, no el punto de entrada. |
| Retornos (día, mes, trimestre, año, 52 semanas) | Más retorno +100 | Momentum, sin excepciones dentro de la familia. La reversión se pide con peso negativo. |
| Caídas desde el máximo y posición en el rango anual | Cerca de máximos +100 | Fortaleza, no ganga. Quien busque castigados usa peso negativo. |
| Peores caídas históricas | Menos profunda +100 | Miden fragilidad. |
| Volumen relativo | Más volumen +100 | Confirma el movimiento. Ver el aviso de cobertura parcial, más abajo. |
| Soporte / resistencia | Soporte cerca y resistencia lejos +100 | El riesgo se acota contra el piso y el recorrido libre está arriba. |
| Múltiplos (P/E, P/B, P/S, cambio del P/E) | Barato +100 | Y **las pérdidas o el patrimonio negativo caen en el peor tramo**, no en el mejor: una empresa que pierde plata no está barata, aunque el número crudo lo parezca. |
| Márgenes, crecimiento, ROIC | Más +100 | Calidad y crecimiento se leen de frente. |

Dos consecuencias de esa tabla que conviene tener presentes al armar una
estrategia:

- **La distancia en σ a la media óptima no es monótona** (premia el retroceso
  sano y castiga tanto el estiramiento como el quiebre). Invertirla con peso
  negativo no da "momentum": premia los dos extremos a la vez.
- **El retorno del mes y el del trimestre son el MISMO número durante el primer
  mes de cada trimestre** (enero, abril, julio, octubre): los dos miden desde la
  última rueda anterior al 1º, que para esos meses coincide. El resto del año
  tampoco son independientes —el trimestre contiene al mes—, así que usarlos
  juntos es doble peso al mismo factor.
- Los umbrales son **puntos de partida de manual**, salvo cinco señales
  —`rvol_daily` y los cuatro retornos— **calibradas sobre la distribución real**
  de una instalación de 498 activos, con los cortes en los percentiles 5 y 95
  medidos. Ninguno es óptimo ni recomendación de inversión.

### Qué se aprendió calibrando

Vale para cualquier umbral que toques después:

- **Lo que importa es cuánto satura, no dónde queda el promedio.** El ranking es
  transversal, así que un puntaje sistemáticamente negativo le resta lo mismo a
  todos y no cambia el orden. Lo que sí destruye orden es el recorte: con la
  escala vieja, el retorno del año dejaba **un tercio** de los activos pegados
  en ±100. Apuntar a ~10% de saturación total (los percentiles 5 y 95) deja la
  masa ordenándose.
- **La excepción es la cobertura parcial.** Ahí el promedio sí importa: si una
  señal vale −58 para el activo mediano y el 4% de los activos no tiene el dato,
  ese 4% se ahorra los −58 y gana el ranking por carecer del dato. Por eso
  `rvol_daily` pasó a tramos centrados en su mediana: con promedio cero, el
  regalo se achica.
- **Una cola larga pide tramos, no rango lineal.** El volumen relativo tiene
  mediana 1 y máximo medido 162: cualquier `range` que cubra ese extremo aplasta
  todo lo demás contra el cero.

### Cobertura parcial: la trampa que hay que mirar

Una señal sin valor **no castiga**: el promedio de la estrategia se calcula
sobre los componentes que sí puntuaron y los pesos se reparten entre ellos, así
que **el activo al que le falta el dato termina sistemáticamente mejor
rankeado**. En este catálogo eso toca dos grupos:

- **`rvol_daily`**: los sintéticos y las conversiones de moneda no tienen
  volumen propio (un cociente entre dos precios no lo tiene).
- **Los 12 fundamentales**: solo puntúan en activos con fundamentales cargados.

Si tu estrategia usa alguno, pedí el dato **también en el filtro de
elegibilidad**: ahí el faltante sí deja al activo afuera, que es lo que querés.
Los ratios fundamentales van en **fracciones** (ROIC 0,15 = 15%).

### Las seis señales sin historia

`drawdown_current`, `drawdown_max1/2/3`, `resistance_pct` y `support_pct` salen
de indicadores que solo guardan **valor vigente**. Sirven para rankear hoy, pero
**no para backtestear**: no hay historia que reconstruir. El validador las marca
con un aviso, y cada una lo dice en su descripción. `drawdown_pct_daily` es la
versión con historia de la primera.

## Cómo se importa

El `senales_base.json` se sube entero a la pantalla **Packs** (`/admin/packs`,
solo admin): ahí están los botones para bajar la especificación y el catálogo, y
subirlo **no escribe nada** — primero se ve el ensayo (errores, avisos, y fila
por fila qué crea y qué actualiza) y recién después se confirma la importación.

La planilla **Excel** va por el camino histórico, sin ensayo previo:
`senales_base_senales.xlsx` en **/admin/signals → Importar**.

Después de importar: en Centro de Datos, card **Señales y Estrategias →
Ejecutar**.

La importación es todo-o-nada **dentro de cada paso**: si alguna fila es
inválida no se escribe ninguna de esa lista y la pantalla muestra el motivo por
fila. Reimportar un archivo actualiza por key (no duplica).

**Reimportar no borra lo que ya está.** El upsert es por `key`, así que las
señales viejas que no figuren en el pack **quedan cargadas** aunque el catálogo
nuevo las reemplace conceptualmente. Sacarlas es un paso aparte, a mano, desde
la pantalla de Señales — y hay que hacerlo mirando qué estrategias las usan.

Visibilidad (migración 0065): la columna **`publica`** (si/no) define si la
señal queda visible para todos los usuarios o solo para su dueño. **Ausente o
vacía = PRIVADA**: publicar es siempre un paso deliberado. El que importa (solo
admin) queda como dueño de las filas nuevas; las existentes conservan su dueño.
Todas las señales de `senales_base` traen `publica=si`. Regla de referencias:
una señal/estrategia pública solo puede referenciar señales públicas.
