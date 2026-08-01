# Strategy packs

Packs listos para importar desde la app (señales y estrategias armadas como
casos de prueba).

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

Cada pack de este directorio está en **los dos formatos**: `<pack>.json` (el
canónico) y sus dos planillas. Se convierten en cualquier dirección, y ninguno
de los dos se edita a mano por separado — se edita uno y se regenera el otro:

```
python scripts/pack_from_json.py strategy_packs/pullback.json   # JSON  → xlsx
python scripts/pack_to_json.py   strategy_packs/pullback        # xlsx → JSON
```

`tests/test_pack_spec.py` verifica que los dos formatos de cada pack digan lo
mismo y que cada uno valide sin errores: si quedan desalineados, falla la
suite.

Políticas:
- **Toda señal debe estar usada por alguna estrategia** — las que no, solo
  agregan costo de procesamiento al pipeline diario y al backfill. El seed
  inicial y el concepto de señal/estrategia "de sistema" se eliminaron
  (migración 0064); todo se gestiona por estos Excel.
- **Cada pack es autosuficiente**: su `<pack>_senales.xlsx` incluye TODAS
  las señales que su estrategia usa (los componentes). Una señal compartida
  por varios packs aparece duplicada en cada uno — el import upsertea por
  key, así que no genera conflicto y el orden entre packs no importa.

## Cómo se importan

El `<pack>.json` se sube entero a la pantalla **Packs** (`/admin/packs`, solo
admin): ahí están los botones para bajar la especificación y el catálogo, y
subirlo **no escribe nada** — primero se ve el ensayo (errores, avisos, y fila
por fila qué crea y qué actualiza) y recién después se confirma la importación,
que aplica las señales y las estrategias en el orden correcto.

Las planillas **Excel** van por el camino histórico, en dos pantallas y sin
ensayo previo:

- `<pack>_senales.xlsx` — se importa primero, en **/admin/signals → Importar**.
- `<pack>_estrategia.xlsx` — se importa después, en **/admin/strategies →
  Importar** (sus componentes referencian las señales del archivo anterior
  por key).

Después de importar: en Centro de Datos, card **Señales y Estrategias →
Ejecutar** (con alcance en la estrategia nueva llena solo su historia).

La importación es todo-o-nada **dentro de cada paso**: si alguna fila es
inválida no se escribe ninguna de esa lista y la pantalla muestra el motivo por
fila. Los dos pasos son transacciones separadas, así que unas señales
importadas quedan aunque falle la estrategia. Reimportar un archivo actualiza
por key/nombre (no duplica).

Visibilidad (migración 0065): la columna **`publica`** (si/no) de cada hoja
define si la señal/estrategia queda visible para todos los usuarios o solo
para su dueño. **Ausente o vacía = PRIVADA**: publicar es siempre un paso
deliberado (antes el default era público, para no romper los packs anteriores a
la columna; se unificó con el default de la UI). El que importa (solo admin)
queda como dueño de las filas nuevas; las existentes conservan su dueño. Todos
los packs de este directorio traen `publica=si` explícito, así que ese cambio
de default no los afecta. Regla de referencias: una señal/estrategia pública
solo puede referenciar señales públicas.

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
quedó afuera del archivo. La razón original —que los ids de catálogo cambian de
base en base— **ya no aplica**: el import resuelve los atributos **por nombre**,
así que hoy se puede escribir en el pack. Lo que sigue dependiendo de la
instalación son los nombres en sí (si ahí no existe un tipo llamado `FUND`, el
import rechaza el archivo entero), así que agregarlo es una decisión de cada
instalación: desde el editor de la estrategia, o en el pack si se sabe qué
tipos hay cargados.

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
| `tendencia_d` / `tendencia_w` / `tendencia_m` (régimen por timeframe) | ⅔ c/u |
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
