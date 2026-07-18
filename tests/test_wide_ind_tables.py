"""Fase 1 de la tabla ancha por cadencia (docs/notes/design_ind_wide_tables.md):
mapping _WIDE + ensure_wide_ind_tables. Todavía nada lee/escribe estas tablas
(el cutover es fase 2-4). Estos tests fijan la clasificación y el esquema.
"""
import sqlalchemy as sa

from app.models.indicator_store import (
    _WIDE, _WIDE_DAILY, _WIDE_MONTHLY, _WIDE_WEEKLY,
    ensure_wide_ind_tables,
)


def test_wide_mapping_cuenta_y_cadencia():
    assert len(_WIDE_DAILY) == 14
    assert len(_WIDE_WEEKLY) == 5
    assert len(_WIDE_MONTHLY) == 5
    assert len(_WIDE) == 24  # sin solapamiento entre cadencias

    for code in _WIDE_DAILY:
        assert _WIDE[code] == ("ind_daily", code, "daily")
    for code in _WIDE_WEEKLY:
        assert _WIDE[code] == ("ind_weekly", code, "weekly")
    for code in _WIDE_MONTHLY:
        assert _WIDE[code] == ("ind_monthly", code, "monthly")


def test_return_periodicos_son_diarios():
    # return_monthly/quarterly/yearly son rolling diarios pese al nombre
    for code in ("return_monthly", "return_quarterly", "return_yearly"):
        assert _WIDE[code][2] == "daily"


def test_wide_cubre_exactamente_los_tecnicos_keep_history():
    """El mapping _WIDE debe coincidir EXACTO con los indicadores técnicos
    keep_history=True del seed (sin fundamentales): atrapa el drift si se agrega
    un indicador con historia y se olvida sumarlo a _WIDE (o viceversa)."""
    from app.services.startup_service import _BUILTIN_INDICATORS

    tecnicos = {
        i["code"] for i in _BUILTIN_INDICATORS
        if i.get("keep_history", True)
        and not i["code"].startswith("fundamental_")
    }
    assert set(_WIDE) == tecnicos


def test_ensure_wide_ind_tables_crea_esquema_e_idempotente():
    eng = sa.create_engine("sqlite://")
    ensure_wide_ind_tables(bind=eng)
    ensure_wide_ind_tables(bind=eng)  # segunda vez: no-op

    insp = sa.inspect(eng)
    for name in ("ind_daily", "ind_weekly", "ind_monthly"):
        assert insp.has_table(name)
        assert insp.get_pk_constraint(name)["constrained_columns"] == [
            "asset_id", "date"]
        assert any(ix["column_names"] == ["date"]
                   for ix in insp.get_indexes(name))

    cols = {c["name"]: c for c in insp.get_columns("ind_daily")}
    assert set(cols) == {"asset_id", "date", *_WIDE_DAILY}
    # tipos: rsi_daily numérico, trend_daily categórico
    assert isinstance(cols["rsi_daily"]["type"], sa.Float)
    assert isinstance(cols["trend_daily"]["type"], sa.String)
