# Strategy packs

Archivos Excel listos para importar desde la app (señales y estrategias
armadas como casos de prueba). Cada pack trae hasta dos archivos:

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

Los parámetros (umbrales, pesos) son puntos de partida de manual para probar
el sistema, no valores optimizados ni recomendación de inversión.
