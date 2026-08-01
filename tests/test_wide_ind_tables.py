"""Fase 1 de la tabla ancha por cadencia (docs/notes/design_ind_wide_tables.md):
mapping _WIDE + ensure_wide_ind_tables. Todavía nada lee/escribe estas tablas
(el cutover es fase 2-4). Estos tests fijan la clasificación y el esquema.
"""
import sqlalchemy as sa

from app.models.indicator_store import (
    _WIDE, _WIDE_DAILY, _WIDE_FUND_DAILY, _WIDE_FUND_QUARTERLY,
    _WIDE_MONTHLY, _WIDE_WEEKLY, ensure_wide_ind_tables,
)


def test_wide_mapping_cuenta_y_cadencia():
    assert len(_WIDE_DAILY) == 19
    assert len(_WIDE_WEEKLY) == 7
    assert len(_WIDE_MONTHLY) == 7
    assert len(_WIDE_FUND_DAILY) == 4
    assert len(_WIDE_FUND_QUARTERLY) == 8
    assert len(_WIDE) == 45  # 33 técnicos + 12 fundamentales

    for code in _WIDE_DAILY:
        assert _WIDE[code] == ("ind_daily", code, "daily")
    for code in _WIDE_WEEKLY:
        assert _WIDE[code] == ("ind_weekly", code, "weekly")
    for code in _WIDE_MONTHLY:
        assert _WIDE[code] == ("ind_monthly", code, "monthly")
    for code in _WIDE_FUND_DAILY:
        assert _WIDE[code] == ("ind_fundamental_daily", code, "fund_daily")
    for code in _WIDE_FUND_QUARTERLY:
        assert _WIDE[code] == ("ind_fundamental_quarterly", code, "fund_quarterly")


def test_return_periodicos_son_diarios():
    # return_monthly/quarterly/yearly son rolling diarios pese al nombre
    for code in ("return_monthly", "return_quarterly", "return_yearly"):
        assert _WIDE[code][2] == "daily"


def test_wide_cubre_exactamente_los_tecnicos_keep_history():
    """El mapping _WIDE (sin los fundamentales) debe coincidir EXACTO con los
    indicadores técnicos keep_history=True del seed: atrapa el drift si se agrega
    un indicador técnico con historia y se olvida sumarlo a _WIDE (o viceversa)."""
    from app.services.startup_service import _BUILTIN_INDICATORS

    tecnicos = {
        i["code"] for i in _BUILTIN_INDICATORS
        if i.get("keep_history", True)
        and not i["code"].startswith("fundamental_")
    }
    fund = set(_WIDE_FUND_DAILY) | set(_WIDE_FUND_QUARTERLY)
    assert set(_WIDE) - fund == tecnicos
    assert fund <= set(_WIDE)  # los 12 fundamentales están en _WIDE
    assert "fundamental_roic" in _WIDE  # trimestral, ahora ancho


def test_atr_pct_y_drawdown_pct_llegan_a_posicionamiento_historico():
    """Los indicadores nuevos de la 0097 tienen que quedar visibles en el tab de
    Posicionamiento Histórico, que filtra por type='num' + keep_history=True
    (distribution_callbacks.update_indicator_options). Es el objetivo del
    cambio: si alguien los pasa a keep_history=False o a type='str',
    desaparecen de la pantalla sin que nada más se rompa."""
    from app.services.startup_service import _BUILTIN_INDICATORS
    from app.services.technical_service import (_BACKFILL_FNS,
                                                _CURRENT_ONLY_CODES)

    nuevos = {"atr_pct_daily", "atr_pct_weekly", "atr_pct_monthly",
              "drawdown_pct_daily"}
    por_code = {i["code"]: i for i in _BUILTIN_INDICATORS}

    for code in nuevos:
        defn = por_code[code]
        assert defn.get("keep_history", True) is True, code
        assert defn["type"] == "num", code
        assert code in _BACKFILL_FNS, code       # hay con qué llenar la historia
        assert code not in _CURRENT_ONLY_CODES, code
        assert code in _WIDE, code


def test_drawdown_con_historia_no_pisa_la_familia_sin_historia():
    """drawdown_current/max1-3 siguen siendo solo-vigentes: la serie nueva no
    los reemplaza (son estadísticos de ella, no la misma lectura)."""
    from app.services.technical_service import _CURRENT_ONLY_CODES

    for code in ("drawdown_current", "drawdown_max1",
                 "drawdown_max2", "drawdown_max3"):
        assert code in _CURRENT_ONLY_CODES
        assert code not in _WIDE


def test_ensure_wide_ind_tables_crea_esquema_e_idempotente():
    eng = sa.create_engine("sqlite://")
    ensure_wide_ind_tables(bind=eng)
    ensure_wide_ind_tables(bind=eng)  # segunda vez: no-op

    insp = sa.inspect(eng)
    for name in ("ind_daily", "ind_weekly", "ind_monthly",
                 "ind_fundamental_daily", "ind_fundamental_quarterly"):
        assert insp.has_table(name)
        assert insp.get_pk_constraint(name)["constrained_columns"] == [
            "asset_id", "date"]
        assert any(ix["column_names"] == ["date"]
                   for ix in insp.get_indexes(name))

    fund_d = {c["name"] for c in insp.get_columns("ind_fundamental_daily")}
    assert fund_d == {"asset_id", "date", *_WIDE_FUND_DAILY}
    fund_q = {c["name"] for c in insp.get_columns("ind_fundamental_quarterly")}
    assert fund_q == {"asset_id", "date", *_WIDE_FUND_QUARTERLY}

    cols = {c["name"]: c for c in insp.get_columns("ind_daily")}
    assert set(cols) == {"asset_id", "date", *_WIDE_DAILY}
    # tipos: rsi_daily numérico, trend_daily categórico
    assert isinstance(cols["rsi_daily"]["type"], sa.Float)
    assert isinstance(cols["trend_daily"]["type"], sa.String)
