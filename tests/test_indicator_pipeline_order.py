"""Orden de fases en rebuild/update_indicator_history.

dist_optimal_sma_* (backfill) depende de best_sma_* (current-only, ver
_query_best_sma / best_sma_cache): calcularlo antes de recomputar
best_sma_* usa el valor de la corrida anterior. rebuild_indicator_history
tuvo ese orden invertido — bug real, corregido. Estos tests lo blindan
sin tocar la base: mockean ambas fases y verifican solo el ORDEN de las
llamadas.
"""
import app.services.technical_service as ts


def _stub_pipeline(monkeypatch, calls):
    monkeypatch.setattr(ts, "get_session", lambda: object())
    # threads (use_procs=False) → _run_current_and_backfill usa _load_all_prices
    monkeypatch.setattr(ts, "_count_price_assets", lambda s: 0)
    monkeypatch.setattr(ts, "_use_process_pool", lambda n: (False, 1))
    monkeypatch.setattr(ts, "_load_all_prices", lambda s: {})
    monkeypatch.setattr(ts, "_refresh_group_scores", lambda: None)
    monkeypatch.setattr(ts, "recompute_current_indicators",
                        lambda **kw: calls.append("current") or {"total": 0, "errors": []})
    monkeypatch.setattr(ts, "backfill_all_indicator_values",
                        lambda **kw: calls.append("backfill") or {"total": 0, "errors": []})


def test_rebuild_corre_current_antes_que_backfill(monkeypatch):
    calls: list = []
    _stub_pipeline(monkeypatch, calls)
    ts.rebuild_indicator_history()
    assert calls == ["current", "backfill"]


def test_update_corre_current_antes_que_backfill(monkeypatch):
    calls: list = []
    _stub_pipeline(monkeypatch, calls)
    ts.update_indicator_history()
    assert calls == ["current", "backfill"]
