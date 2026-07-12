# Strategy packs

Archivos Excel listos para importar desde la app (señales y estrategias
armadas como casos de prueba).

Política: **toda señal debe estar usada por alguna estrategia** — las que
no, solo agregan costo de procesamiento al pipeline diario y al backfill.
El seed inicial y el concepto de señal/estrategia "de sistema" se
eliminaron (migración 0064); todo se gestiona por estos Excel.

## base_senales.xlsx — importar SIEMPRE primero

Las 6 señales compartidas que las estrategias de los packs referencian:
`tendencia_d/w/m` (las w/m por la composite), `rsi_señal`, `dist_sma_d` y
`alineacion_timeframes`.

Cada pack trae hasta dos archivos:

- `<pack>_senales.xlsx` — se importa primero, en **/admin/signals → Importar**.
  Solo incluye las señales que no existen como señales de sistema.
- `<pack>_estrategia.xlsx` — se importa después, en **/admin/strategies →
  Importar** (sus componentes referencian señales por key: las del archivo
  anterior más las de sistema, así que el orden importa).

Después de importar: **/admin/signals → Ejecutar pipeline** para calcular los
scores del día, y en **/admin/strategies → Calcular resultados** para ver el
ranking.

La importación es todo-o-nada: si alguna fila es inválida no se escribe nada
y la pantalla muestra el motivo por fila. Reimportar un archivo actualiza por
key/nombre (no duplica).

## pullback_en_tendencia

Compra retrocesos de corto plazo dentro de tendencias alcistas confirmadas.

**Filtro de elegibilidad** (AND):
- `trend_weekly` in [bullish, bullish_strong, bullish_nascent_strong]
- `dist_sma200` > 0 (precio sobre la media de 200 ruedas)
- `volatility_daily` not in [extrema_corta, extrema_media, extrema_larga]

**Ranking** (promedio ponderado):

| Señal | Peso | Origen |
|---|---|---|
| `rsi_señal` (RSI invertido: sobreventa → +100) | 3 | sistema, ya existe |
| `fuerza_relativa_52w` (>20 → 100, >0 → 50, resto → −50) | 2 | pack |
| `dist_sma_pullback_d` (2σ arriba → −100, 2σ abajo → +100) | 2 | pack |
| `tendencia_d` (mapa de régimen diario) | 1 | sistema, ya existe |

Nota: el filtro por tipo de instrumento (`instrument_type in [Equity, FUND]`)
quedó afuera del archivo a propósito — los ids de catálogo dependen de cada
base. Agregarlo a mano desde el editor de la estrategia si se quiere.

## momentum_de_lideres

Contracara del Pullback: compra los activos MÁS fuertes del mismo universo
(mismo filtro de elegibilidad), en vez de los que retrocedieron. Al
compartir filtro, cualquier diferencia de resultados entre ambas es
atribuible 100% al ranking — ideal para comparar filosofías.

**Requiere el pack pullback importado antes** (reutiliza la señal
`fuerza_relativa_52w`).

**Ranking** (promedio ponderado):

| Señal | Peso | Origen |
|---|---|---|
| `retorno_52w` (range −20%→−100 ... +80%→+100) | 3 | pack |
| `fuerza_relativa_52w` | 2 | pack pullback |
| `alineacion_timeframes` (composite tendencia d/w/m) | 2 | sistema |
| `dist_sma_d` (premia extensión sobre la SMA óptima, sin invertir) | 1 | sistema |

## garp_calidad_precio

Calidad a precio razonable, la primera estrategia que usa la dimensión
fundamental. El filtro por P/E (>0 y <60) restringe el universo a activos
con fundamentales cargados y rentables; el resto del filtro es técnico
suave (dist_sma200 > −10, sin volatilidad extrema).

| Señal | Peso | Origen |
|---|---|---|
| `roic_calidad` (ROIC TTM: >20% → 100 ... negativo → −80) | 3 | pack |
| `pe_razonable` (P/E: <8 → 100 ... >40 → −80, pérdidas → −100) | 3 | pack |
| `crecimiento_ventas` (revenue YoY: −10% → −100, +30% → +100) | 2 | pack |
| `tendencia_m` (tendencia mensual, desempate técnico) | 1 | sistema |

Nota: los ratios fundamentales van en fracciones (ROIC 0.15 = 15%).

## pullback_bajista

Espejo exacto del Pullback en tendencia, para cortos o como lista de
"evitar": tendencia semanal bajista + precio bajo la SMA200 + sin
volatilidad extrema, rankeando el rebote de corto plazo.

| Señal | Peso | Origen |
|---|---|---|
| `rsi_rebote` (sobrecompra → +100: rally para shortear) | 3 | pack |
| `debilidad_relativa_52w` (perder contra el benchmark → +100) | 2 | pack |
| `dist_sma_d` (SIN invertir: extendido sobre su SMA = resistencia) | 2 | sistema |
| `tendencia_d_bajista` (mapa de régimen con signos invertidos) | 1 | pack |

Los parámetros (umbrales, pesos) son puntos de partida de manual para probar
el sistema, no valores optimizados ni recomendación de inversión.
