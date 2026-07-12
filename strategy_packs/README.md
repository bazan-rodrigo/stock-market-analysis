# Strategy packs

Archivos Excel listos para importar desde la app (señales y estrategias
armadas como casos de prueba).

Políticas:
- **Toda señal debe estar usada por alguna estrategia** — las que no, solo
  agregan costo de procesamiento al pipeline diario y al backfill. El seed
  inicial y el concepto de señal/estrategia "de sistema" se eliminaron
  (migración 0064); todo se gestiona por estos Excel.
- **Cada pack es autosuficiente**: su `<pack>_senales.xlsx` incluye TODAS
  las señales que su estrategia usa (componentes + dependencias de
  composites). Una señal compartida por varios packs aparece duplicada en
  cada uno — el import upsertea por key, así que no genera conflicto y el
  orden entre packs no importa.

Cada pack trae dos archivos:

- `<pack>_senales.xlsx` — se importa primero, en **/admin/signals → Importar**.
- `<pack>_estrategia.xlsx` — se importa después, en **/admin/strategies →
  Importar** (sus componentes referencian las señales del archivo anterior
  por key).

Después de importar: en Centro de Datos, card **Señales y Estrategias →
Ejecutar** (con alcance en la estrategia nueva llena solo su historia).

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

| Señal | Peso |
|---|---|
| `rsi_señal` (RSI invertido: sobreventa → +100) | 3 |
| `fuerza_relativa_52w` (>20 → 100, >0 → 50, resto → −50) | 2 |
| `dist_sma_pullback_d` (2σ arriba → −100, 2σ abajo → +100) | 2 |
| `tendencia_d` (mapa de régimen diario) | 1 |

Nota: el filtro por tipo de instrumento (`instrument_type in [Equity, FUND]`)
quedó afuera del archivo a propósito — los ids de catálogo dependen de cada
base. Agregarlo a mano desde el editor de la estrategia si se quiere.

## momentum_de_lideres

Contracara del Pullback: compra los activos MÁS fuertes del mismo universo
(mismo filtro de elegibilidad), en vez de los que retrocedieron. Al
compartir filtro, cualquier diferencia de resultados entre ambas es
atribuible 100% al ranking — ideal para comparar filosofías.

**Ranking** (promedio ponderado):

| Señal | Peso |
|---|---|
| `retorno_52w` (range −20%→−100 ... +80%→+100) | 3 |
| `fuerza_relativa_52w` | 2 |
| `alineacion_timeframes` (composite de `tendencia_d/w/m`, incluidas) | 2 |
| `dist_sma_d` (premia extensión sobre la SMA óptima, sin invertir) | 1 |

## garp_calidad_precio

Calidad a precio razonable, la primera estrategia que usa la dimensión
fundamental. El filtro por P/E (>0 y <60) restringe el universo a activos
con fundamentales cargados y rentables; el resto del filtro es técnico
suave (dist_sma200 > −10, sin volatilidad extrema).

| Señal | Peso |
|---|---|
| `roic_calidad` (ROIC TTM: >20% → 100 ... negativo → −80) | 3 |
| `pe_razonable` (P/E: <8 → 100 ... >40 → −80, pérdidas → −100) | 3 |
| `crecimiento_ventas` (revenue YoY: −10% → −100, +30% → +100) | 2 |
| `tendencia_m` (tendencia mensual, desempate técnico) | 1 |

Nota: los ratios fundamentales van en fracciones (ROIC 0.15 = 15%).

## pullback_bajista

Espejo exacto del Pullback en tendencia, para cortos o como lista de
"evitar": tendencia semanal bajista + precio bajo la SMA200 + sin
volatilidad extrema, rankeando el rebote de corto plazo.

| Señal | Peso |
|---|---|
| `rsi_rebote` (sobrecompra → +100: rally para shortear) | 3 |
| `debilidad_relativa_52w` (perder contra el benchmark → +100) | 2 |
| `dist_sma_d` (SIN invertir: extendido sobre su SMA = resistencia) | 2 |
| `tendencia_d_bajista` (mapa de régimen con signos invertidos) | 1 |

Los parámetros (umbrales, pesos) son puntos de partida de manual para probar
el sistema, no valores optimizados ni recomendación de inversión.
