"""check_sanity: chequeos de cordura independientes del delta — ¿el valor
tiene sentido para ese código, sin importar cómo se calculó?"""
from datetime import date, timedelta

from app.services.fundamental_service import _Quarter
from app.services.verification_service import (
    _aggregate_flags, _current_ratio_diff_entry, _current_ratio_fresh,
    _diff_category, _flag_actions, _values_equal, check_sanity,
)


def _q(period_date, **kw):
    fields = {f: None for f in _Quarter._fields if f != "period_date"}
    fields.update(kw)
    return _Quarter(period_date=period_date, **fields)


def test_rsi_en_rango_no_dispara():
    assert check_sanity("rsi_daily", 55.3) is None
    assert check_sanity("rsi_daily", 0) is None
    assert check_sanity("rsi_daily", 100) is None


def test_rsi_fuera_de_rango_dispara():
    assert check_sanity("rsi_daily", 150) is not None
    assert check_sanity("rsi_weekly", -5) is not None


def test_atr_percentile_fuera_de_rango_dispara():
    assert check_sanity("atr_percentile_monthly", 101) is not None


def test_trend_categoria_valida_no_dispara():
    for v in ("bullish", "bearish", "lateral", "bullish_nascent_strong"):
        assert check_sanity("trend_daily", v) is None


def test_trend_categoria_desconocida_dispara():
    assert check_sanity("trend_daily", "sideways") is not None


def test_volatility_categoria_valida_no_dispara():
    assert check_sanity("volatility_weekly", "alta_larga") is None


def test_volatility_categoria_desconocida_dispara():
    assert check_sanity("volatility_weekly", "muy_alta_larga") is not None


def test_return_extremo_dispara():
    assert check_sanity("return_daily", 50000) is not None


def test_return_razonable_no_dispara():
    assert check_sanity("return_daily", -8.5) is None


def test_fundamental_margin_extremo_dispara():
    assert check_sanity("fundamental_net_margin", 500) is not None


def test_fundamental_margin_razonable_no_dispara():
    assert check_sanity("fundamental_net_margin", 0.15) is None


def test_codigo_sin_bounds_conocidos_no_dispara():
    # un código sin entrada en _NUMERIC_BOUNDS/_CATEGORICAL_VALUES no se
    # puede validar — no dispara falso positivo
    assert check_sanity("codigo_inventado_sin_bounds", "cualquier cosa") is None


def test_valor_none_no_dispara():
    assert check_sanity("rsi_daily", None) is None


# ── _values_equal: tolerancia absoluta + relativa ─────────────────────────────
# ind_fundamental_* guarda en una columna Float (FLOAT de MySQL, precisión
# simple) — para ratios de magnitud grande (pesos ARS/CLP) el redondeo de
# la propia columna ya supera 0.01 sin que sea un bug de cálculo.

def test_values_equal_dentro_de_tolerancia_absoluta():
    assert _values_equal(1.005, 1.01)


def test_values_equal_fuera_de_tolerancia_absoluta_magnitud_chica():
    assert not _values_equal(1.0, 1.5)


def test_values_equal_tolerancia_relativa_para_magnitudes_grandes():
    assert _values_equal(35955.5556, 35955.6)


def test_values_equal_diferencia_relativa_grande_si_dispara():
    assert not _values_equal(100.0, 200.0)


# ── _current_ratio_fresh: replica _compute_current_ratios (fundamental_
# service.py) en modo lectura — el ratio "vigente" que el sistema real
# escribe con fecha de hoy usando el último trimestre + último precio,
# sea o no hoy un cierre de trimestre o una fecha con precio propio.

def test_current_ratio_fresh_usa_ultimo_trimestre_y_ultimo_precio():
    today = date.today()
    quarters = [
        _q(today - timedelta(days=400), net_income=100, revenue=500,
           equity=1000, shares=100),
        _q(today - timedelta(days=100), net_income=120, revenue=550,
           equity=1100, shares=100),
    ]
    price_rows = [(today - timedelta(days=5), 50.0)]
    fresh = _current_ratio_fresh(quarters, price_rows)
    assert fresh["fundamental_pb"] == round(50.0 / (1100 / 100), 4)


def test_current_ratio_fresh_sin_quarters_devuelve_vacio():
    assert _current_ratio_fresh([], [(date.today(), 50.0)]) == {}


def test_current_ratio_fresh_sin_precio_no_agrega_ratios_diarios():
    today = date.today()
    quarters = [_q(today - timedelta(days=100), net_income=120, revenue=550,
                   equity=1100, shares=100, total_debt=200)]
    fresh = _current_ratio_fresh(quarters, [])
    assert "fundamental_pe_ttm" not in fresh
    assert "fundamental_pb" not in fresh
    # los trimestrales sí se calculan aunque no haya precio
    assert "fundamental_debt_to_equity" in fresh


# ── _diff_category: separa "sospecha de bug de caché" de "dato de origen
# raro" — guardado != recalculado es lo primero (el propósito real de esta
# herramienta); guardado == recalculado pero fuera de rango es lo segundo
# (ver hallazgos reales: ITX.MC precio corrupto, CMPC.SN P/E con <4
# trimestres) y no debería mezclarse con sospechas de bug de caché/delta.

def test_diff_category_discrepancia_de_valor_es_calc():
    assert _diff_category("valor distinto") == "calc"
    assert _diff_category("solo en DB (¿debería haberse borrado?)") == "calc"
    assert _diff_category("falta en DB (¿el delta no la escribió?)") == "calc"


def test_diff_category_sanity_es_cualquier_otro_motivo():
    assert _diff_category("fuera de rango [0,100] para rsi_daily: 150") == "sanity"
    assert _diff_category("categoría desconocida para trend_daily: 'sideways'") == "sanity"


# ── _current_ratio_diff_entry: el "vigente" se reescribe con la fecha del
# día en que corrió producción, no una fecha fija — comparar contra "hoy"
# a secas daría una diferencia falsa cada vez que la verificación no corre
# el mismo día que el último refresh de producción (prácticamente siempre).

def test_current_ratio_diff_entry_none_sin_valor_vigente():
    assert _current_ratio_diff_entry(None, {date(2026, 7, 9): 1.5}, date(2026, 7, 10)) is None


def test_current_ratio_diff_entry_usa_la_fecha_mas_reciente_guardada():
    # no "hoy" -- el vigente se reescribe con la fecha del dia en que
    # corrio produccion, no una fecha fija
    stored = {date(2026, 7, 8): 1.2, date(2026, 7, 9): 1.5}
    entry = _current_ratio_diff_entry(1.8, stored, date(2026, 7, 10))
    assert entry == (date(2026, 7, 9), 1.8)


def _diff(cat, code_date=date(2026, 1, 1)):
    return (code_date, "motivo", "guardado", "fresco", cat)


# ── _aggregate_flags: agrupa resultados de run_verification/
# run_fund_verification por activo -- fuente de asset_verification_flag
# (ver run_full_verification_and_store) que marca los selectores de
# activo con posibles hallazgos.

def test_aggregate_flags_cuenta_por_categoria():
    result = {"results": [
        {"code": "rsi_daily", "asset_id": 1, "ticker": "AAPL",
         "diffs": [_diff("calc"), _diff("calc"), _diff("sanity")]},
    ]}
    agg = _aggregate_flags(result)
    assert agg[1]["calc"] == 2
    assert agg[1]["sanity"] == 1
    assert agg[1]["codes"] == {"rsi_daily"}


def test_aggregate_flags_combina_varios_resultados_del_mismo_activo():
    # indicadores + fundamentales para el mismo activo -- típico de
    # run_full_verification_and_store, que llama run_verification y
    # run_fund_verification por separado
    ind  = {"results": [{"code": "rsi_daily", "asset_id": 1, "ticker": "AAPL",
                         "diffs": [_diff("sanity")]}]}
    fund = {"results": [{"code": "fundamental_pe_ttm", "asset_id": 1, "ticker": "AAPL",
                         "diffs": [_diff("calc")]}]}
    agg = _aggregate_flags(ind, fund)
    assert agg[1]["calc"] == 1
    assert agg[1]["sanity"] == 1
    assert agg[1]["codes"] == {"rsi_daily", "fundamental_pe_ttm"}


def test_aggregate_flags_activos_distintos_no_se_mezclan():
    result = {"results": [
        {"code": "rsi_daily", "asset_id": 1, "ticker": "AAPL", "diffs": [_diff("calc")]},
        {"code": "rsi_daily", "asset_id": 2, "ticker": "MSFT", "diffs": [_diff("sanity")]},
    ]}
    agg = _aggregate_flags(result)
    assert set(agg) == {1, 2}
    assert agg[1]["calc"] == 1 and agg[1]["sanity"] == 0
    assert agg[2]["sanity"] == 1 and agg[2]["calc"] == 0


def test_aggregate_flags_sin_resultados_es_vacio():
    assert _aggregate_flags({"results": []}) == {}


# ── _flag_actions: decide upsert/delete por activo re-verificado -- la
# marca de un activo se reescribe exactamente cuando ESE activo se vuelve
# a verificar (corrida completa o re-verificación puntual), nunca antes.

def test_flag_actions_sigue_con_hallazgos_es_upsert():
    scope = {1}
    by_asset = {1: {"calc": 1, "sanity": 0, "codes": {"rsi_daily"}}}
    to_upsert, to_delete = _flag_actions(scope, by_asset, existing_ids=set())
    assert to_upsert == {1}
    assert to_delete == set()


def test_flag_actions_ya_no_tiene_hallazgos_y_tenia_fila_es_delete():
    scope = {1}
    to_upsert, to_delete = _flag_actions(scope, by_asset={}, existing_ids={1})
    assert to_upsert == set()
    assert to_delete == {1}


def test_flag_actions_sin_hallazgos_y_sin_fila_previa_no_hace_nada():
    scope = {1}
    to_upsert, to_delete = _flag_actions(scope, by_asset={}, existing_ids=set())
    assert to_upsert == set()
    assert to_delete == set()


def test_flag_actions_fuera_de_scope_no_se_toca():
    # activo 2 tiene hallazgos pero no esta en el scope re-verificado (p.
    # ej. una reverificacion puntual de "solo los marcados" que no lo
    # incluia) -- no debe aparecer en ninguna de las dos listas
    scope = {1}
    by_asset = {1: {"calc": 0, "sanity": 1, "codes": {"return_daily"}},
                2: {"calc": 1, "sanity": 0, "codes": {"rsi_daily"}}}
    to_upsert, to_delete = _flag_actions(scope, by_asset, existing_ids={1, 2})
    assert to_upsert == {1}
    assert to_delete == set()


def test_current_ratio_diff_entry_sin_nada_guardado_usa_hoy():
    entry = _current_ratio_diff_entry(1.5, {}, date(2026, 7, 10))
    assert entry == (date(2026, 7, 10), 1.5)


def test_current_ratio_diff_entry_coincide_no_genera_diff_en_el_loop():
    # el propio valor de entry no distingue "coincide" de "difiere" --
    # eso lo resuelve _values_equal en el loop de verify_asset_ratio_code
    # (fv == sv -> ninguna rama dispara). Acá solo verificamos que SIEMPRE
    # se devuelve una entrada con la fecha guardada (nunca None) cuando
    # hay valor vigente y algo guardado, aunque coincidan: si se
    # "saltease" el agregado por coincidir, esa fecha quedaría en
    # `stored` sin contraparte en `fresh` y el loop la marcaría como
    # "solo en DB" -- justamente el bug que esto reemplaza.
    stored = {date(2026, 7, 9): 1.5}
    entry = _current_ratio_diff_entry(1.5, stored, date(2026, 7, 10))
    assert entry == (date(2026, 7, 9), 1.5)
    assert _values_equal(entry[1], stored[entry[0]])
