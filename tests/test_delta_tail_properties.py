"""Property-based (hypothesis) para las invariantes del camino rápido del
delta — complementa test_delta_tail.py, que usa ejemplos elegidos a mano.

La motivación es concreta: el bug de _checksum_prefix ([:-1] guardado vs
[:k] comparado, commit a41c012) se encontró con datos reales de
producción, no con los tests de ejemplo — una propiedad como
test_checksum_guardado_coincide_con_comparacion_siguiente_corrida lo
hubiera encontrado sola, generando miles de combinaciones de fechas/huecos
en vez de depender de que apareciera primero en el Codespace.
"""
from datetime import date, timedelta

from hypothesis import given, settings, strategies as st

from app.services.technical_service import (
    _checksum_prefix, _confirmed_empty_fast_path, _delta_tail_start,
    _pairs_to_write, _series_checksum, _stale_dates_to_delete,
)

_MAX_EXAMPLES = 300

# Fechas ascendentes sin huecos de calendario (simplifica la generación:
# lo que varía entre ejemplos es CUÁLES tienen valor válido, no el
# calendario en sí — igual que hace _fechas() en test_delta_tail.py).
_dates_strategy = st.integers(min_value=2, max_value=60).map(
    lambda n: [date(2024, 1, 1) + timedelta(days=i) for i in range(n)]
)


# ── _checksum_prefix: lo que se guarda tiene que ser lo que se compara ───────
# la próxima corrida (ver _delta_tail_start) — esta es la propiedad que el
# bug real de la sesión rompía.

@given(dates=_dates_strategy, data=st.data())
@settings(max_examples=_MAX_EXAMPLES, deadline=None)
def test_checksum_guardado_coincide_con_comparacion_siguiente_corrida(dates, data):
    i = data.draw(st.integers(min_value=0, max_value=len(dates) - 1))
    own_mx = dates[i]
    vals = data.draw(st.lists(
        st.one_of(st.none(), st.floats(min_value=-1e6, max_value=1e6, allow_nan=False)),
        min_size=len(dates), max_size=len(dates),
    ))

    stored = _checksum_prefix(dates, vals, own_mx)

    # Simula la corrida siguiente: el prefijo [0..i] quedó guardado sin
    # huecos de calendario (mn=dates[0], mx=own_mx, cnt=i+1) — mismo
    # supuesto que usa _delta_tail_start en modo "series".
    stat = (dates[0], own_mx, i + 1)
    k = _delta_tail_start(dates, stat, "series")

    assert k == i
    assert _series_checksum(vals[:k]) == stored


@given(dates=_dates_strategy, data=st.data())
@settings(max_examples=_MAX_EXAMPLES, deadline=None)
def test_checksum_prefix_nunca_incluye_la_propia_ultima_fecha_valida(dates, data):
    i = data.draw(st.integers(min_value=0, max_value=len(dates) - 1))
    own_mx = dates[i]
    vals = data.draw(st.lists(
        st.floats(min_value=-1e6, max_value=1e6, allow_nan=False),
        min_size=len(dates), max_size=len(dates),
    ))
    # el checksum de [:i] no puede depender del valor en la posición i
    stored_a = _checksum_prefix(dates, vals, own_mx)
    vals_b = list(vals)
    vals_b[i] = vals_b[i] + 1.0  # cambia SOLO el valor en own_mx
    stored_b = _checksum_prefix(dates, vals_b, own_mx)
    assert stored_a == stored_b


# ── _pairs_to_write: el modo set nunca reescribe una fecha existente ─────────
# salvo la última (regla del "precio preliminar").

@given(dates=_dates_strategy, data=st.data())
@settings(max_examples=_MAX_EXAMPLES, deadline=None)
def test_pairs_to_write_set_respeta_existing_salvo_la_ultima(dates, data):
    vals = data.draw(st.lists(
        st.one_of(st.none(), st.floats(min_value=-1e6, max_value=1e6, allow_nan=False)),
        min_size=len(dates), max_size=len(dates),
    ))
    existing = set(data.draw(st.lists(st.sampled_from(dates), unique=True)))

    pairs = _pairs_to_write(dates, vals, existing)
    written_dates = {d for d, _ in pairs}
    last_d = dates[-1]

    # todo lo escrito está en el calendario y tiene valor válido
    assert written_dates <= set(dates)
    val_by_date = dict(zip(dates, vals))
    for d, v in pairs:
        assert val_by_date[d] == v or (val_by_date[d] is not None and v is not None)

    # ninguna fecha ya existente (salvo la última) se reescribe
    assert (written_dates & existing) <= {last_d}


# ── _stale_dates_to_delete: completitud — atrapa TODAS las fechas ───────────
# obsoletas (guardadas + valor ahora inválido), ni una de más ni una de menos.

@given(dates=_dates_strategy, data=st.data())
@settings(max_examples=_MAX_EXAMPLES, deadline=None)
def test_stale_dates_completo_y_exacto(dates, data):
    vals = data.draw(st.lists(
        st.one_of(st.none(), st.floats(min_value=-1e6, max_value=1e6, allow_nan=False)),
        min_size=len(dates), max_size=len(dates),
    ))
    existing = set(data.draw(st.lists(st.sampled_from(dates), unique=True)))

    stale = set(_stale_dates_to_delete(dates, vals, existing))
    val_by_date = dict(zip(dates, vals))

    expected = {d for d in existing if val_by_date[d] is None}
    assert stale == expected


# ── _confirmed_empty_fast_path: solo dispara con confirmación previa real ───

@given(
    stats_now_none=st.booleans(),
    cached=st.one_of(
        st.none(),
        st.tuples(st.dates(), st.dates(), st.integers(min_value=0, max_value=10000)),
    ),
)
def test_confirmed_empty_solo_dispara_si_cached_confirma_cero(stats_now_none, cached):
    stats = None if stats_now_none else (date(2025, 1, 1), date(2025, 1, 2), 1)
    result = _confirmed_empty_fast_path(stats, cached)
    esperado = stats_now_none and cached is not None and cached[2] == 0
    assert result == esperado
