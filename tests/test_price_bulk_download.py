"""Camino batch de descarga de precios.

update_new_assets_prices ("solo nuevos"), update_all_active_assets y
redownload_prices global comparten _bulk_download_assets (prefetch batch de
Yahoo + escritura en ThreadPool). Estos tests fijan la ORQUESTACIÓN — qué se
llama, con qué argumentos y en qué orden — con monkeypatch (patrón de
test_indicator_pipeline_order); la descarga real se prueba en el Codespace.
También la semántica full=True del worker (la historia previa solo se borra
si la descarga trajo datos), esa sí contra el stub sqlite.
"""
import sys
import types
from datetime import date

# price_service (vía app.sources.yahoo) importa yfinance en el header; esta
# PC y la suite no lo tienen — un stub vacío alcanza: acá nunca se descarga.
sys.modules.setdefault("yfinance", types.ModuleType("yfinance"))

import pandas as pd
import pytest
import sqlalchemy as sa

from app.database import Base, engine, get_session
from app.models import Asset, Price, PriceSource, PriceUpdateLog
from app.services import price_service as ps

_TABLES = ("price_update_log", "prices", "synthetic_formula", "assets")


@pytest.fixture()
def db():
    import app.models  # noqa: F401 — registra los modelos en Base.metadata
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for t in _TABLES:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    yield
    with engine.begin() as conn:
        for t in _TABLES:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    get_session().rollback()


def _get_or_create_source(name):
    s = get_session()
    src = s.query(PriceSource).filter_by(name=name).first()
    if src is None:
        src = PriceSource(name=name)
        s.add(src)
        s.commit()
    return src.id


def _seed_assets(n_yf=0, n_other=0, with_log=(), prefix="BULK"):
    """Crea activos Yahoo/otra-fuente; with_log = índices (sobre el total)
    que nacen con PriceUpdateLog (o sea: NO son 'nuevos')."""
    s = get_session()
    yf_id    = _get_or_create_source("Yahoo Finance")
    other_id = _get_or_create_source("OtraFuente")
    created = []
    for i in range(n_yf + n_other):
        a = Asset(ticker=f"{prefix}{i}", name=f"{prefix}{i}",
                  price_source_id=yf_id if i < n_yf else other_id)
        s.add(a)
        s.flush()
        created.append((a.id, a.ticker))
        if i in with_log:
            s.add(PriceUpdateLog(asset_id=a.id, success=True))
    s.commit()
    return created


def _patch_cfgs(monkeypatch):
    for cfg in ("_get_drawdown_config", "_get_regime_config",
                "_get_volatility_config"):
        monkeypatch.setattr(ps, cfg, lambda: None)
    monkeypatch.setattr(ps.sr_service, "_get_sr_config", lambda: None)


def _patch_workers(monkeypatch, events):
    def fake_prefetch(assets_with_dates):
        events.append(("prefetch",
                       sorted(a.ticker for a, _ in assets_with_dates),
                       sorted((a.ticker, d) for a, d in assets_with_dates)))
        return {a.id: f"df-{a.ticker}" for a, _ in assets_with_dates}

    def fake_yf(asset_id, ticker, df, last_date, _dd_cfg=None, _regime_cfg=None,
                _vol_cfg=None, _sr_cfg=None, skip_indicators=False, full=False):
        events.append(("yf", ticker, df, last_date, skip_indicators, full))
        return True, None

    def fake_other(asset_id, ticker, _dd_cfg=None, _regime_cfg=None,
                   _vol_cfg=None, _sr_cfg=None, skip_indicators=False,
                   full=False):
        events.append(("other", ticker, skip_indicators, full))
        return True, None

    monkeypatch.setattr(ps, "_bulk_prefetch_yfinance", fake_prefetch)
    monkeypatch.setattr(ps, "_process_yf_asset_worker", fake_yf)
    monkeypatch.setattr(ps, "_process_other_asset_worker", fake_other)


# ── "Solo nuevos" va por el camino batch ─────────────────────────────────────

def test_solo_nuevos_prefetch_batch_workers_y_delta_al_final(db, monkeypatch):
    created = _seed_assets(n_yf=3, n_other=1, with_log={2})
    nuevos_yf    = [t for i, (_, t) in enumerate(created) if i in (0, 1)]
    nuevo_other  = created[3][1]

    events = []
    _patch_cfgs(monkeypatch)
    _patch_workers(monkeypatch, events)
    monkeypatch.setattr(
        ps, "_chain_to_indicator_and_ratio_delta",
        lambda cb, summary: (events.append(("chain", dict(summary))) or summary))

    out = ps.update_new_assets_prices()

    # El prefetch corre UNA vez, solo con los Yahoo nuevos, todos sin fecha
    prefetches = [e for e in events if e[0] == "prefetch"]
    assert len(prefetches) == 1
    assert prefetches[0][1] == sorted(nuevos_yf)
    assert prefetches[0][2] == sorted((t, None) for t in nuevos_yf)

    # Cada Yahoo nuevo se procesa con su df prefetcheado, sin indicadores
    yf_calls = sorted(e for e in events if e[0] == "yf")
    assert yf_calls == sorted(
        ("yf", t, f"df-{t}", None, True, False) for t in nuevos_yf)

    # El de otra fuente va por su worker; el que tenía log NO aparece
    assert [e for e in events if e[0] == "other"] == \
        [("other", nuevo_other, True, False)]
    assert not any(created[2][1] in str(e) for e in events)

    # El delta se encadena AL FINAL, con el resumen de la descarga
    assert events[-1][0] == "chain"
    assert events[-1][1] == {"total": 3, "success": 3, "errors": []}
    assert out == {"total": 3, "success": 3, "errors": []}


def test_solo_nuevos_sin_activos_nuevos_no_encadena_nada(db, monkeypatch):
    _seed_assets(n_yf=1, with_log={0})
    events = []
    _patch_cfgs(monkeypatch)
    _patch_workers(monkeypatch, events)
    out = ps.update_new_assets_prices()
    assert events == []                     # ni prefetch ni workers
    assert out == {"total": 0, "success": 0, "errors": []}


# ── update_all_active_assets conserva su cadena posterior ────────────────────

def test_actualizar_todos_delega_en_bulk_y_conserva_cadena(db, monkeypatch):
    created = _seed_assets(n_yf=2, with_log={0})   # con y sin log: entran todos
    calls = []

    def fake_bulk(assets, progress_cb=None, full=False):
        calls.append(("bulk", sorted(a.ticker for a in assets), full))
        return {"total": len(assets), "success": len(assets), "errors": []}

    import app.services.fundamental_service as fs
    import app.services.technical_service as ts
    monkeypatch.setattr(ps, "_bulk_download_assets", fake_bulk)
    monkeypatch.setattr(
        ts, "update_indicator_history",
        lambda progress_cb=None: (calls.append("ind")
                                  or {"total": 1, "success": 1, "errors": []}))
    monkeypatch.setattr(
        fs, "update_all_fundamentals",
        lambda progress_cb=None: (calls.append("fund")
                                  or {"total": 1, "success": 1, "errors": []}))
    monkeypatch.setattr(ts, "_refresh_group_scores",
                        lambda: calls.append("groups"))

    out = ps.update_all_active_assets()

    assert calls[0] == ("bulk", sorted(t for _, t in created), False)
    assert calls[1:] == ["ind", "fund", "groups"]
    assert out["total"] == len(created) + 2    # descarga + ind + fund


# ── Redescarga global batch full=True; puntual sigue secuencial ──────────────

def test_redescarga_global_va_batch_full_y_encadena_delta(db, monkeypatch):
    created = _seed_assets(n_yf=2)
    calls = []

    def fake_bulk(assets, progress_cb=None, full=False):
        calls.append(("bulk", sorted(a.ticker for a in assets), full))
        return {"total": len(assets), "success": len(assets), "errors": []}

    monkeypatch.setattr(ps, "_bulk_download_assets", fake_bulk)
    monkeypatch.setattr(
        ps, "_chain_to_indicator_and_ratio_delta",
        lambda cb, summary: (calls.append("chain") or summary))

    out = ps.redownload_prices(None)
    assert calls == [("bulk", sorted(t for _, t in created), True), "chain"]
    assert out["total"] == len(created)


def test_redescarga_puntual_sigue_secuencial(db, monkeypatch):
    (aid, _), = _seed_assets(n_yf=1)
    calls = []
    monkeypatch.setattr(ps, "_bulk_download_assets",
                        lambda *a, **k: calls.append("bulk"))
    monkeypatch.setattr(
        ps, "update_asset_prices",
        lambda asset_id, full=False, skip_indicators=False, **k:
            calls.append(("seq", asset_id, full, skip_indicators)))
    monkeypatch.setattr(
        ps, "_rebuild_indicators_for_assets",
        lambda cb, ids: (calls.append(("rebuild", list(ids)))
                         or {"total": 0, "success": 0, "errors": []}))

    ps.redownload_prices([aid])
    assert calls == [("seq", aid, True, True), ("rebuild", [aid])]


def test_bulk_full_ignora_fechas_existentes(db, monkeypatch):
    created = _seed_assets(n_yf=1)
    aid, ticker = created[0]
    s = get_session()
    s.add(Price(asset_id=aid, date=date(2026, 1, 2), close=10.0))
    s.commit()

    events = []
    _patch_cfgs(monkeypatch)
    _patch_workers(monkeypatch, events)

    assets = get_session().query(Asset).filter(Asset.id == aid).all()
    ps._bulk_download_assets(assets, full=True)

    # A pesar de tener precios, con full=True el prefetch lo ve sin fecha
    # (grupo first_time → historia completa) y el worker recibe full=True
    assert [e for e in events if e[0] == "prefetch"][0][2] == [(ticker, None)]
    assert [e for e in events if e[0] == "yf"] == \
        [("yf", ticker, f"df-{ticker}", None, True, True)]


def test_yahoo_fuera_del_prefetch_cae_al_fallback_con_full(db, monkeypatch):
    # Un activo Yahoo cuyo chunk de descarga falló NO aparece en el prefetch:
    # debe caer a _process_other_asset_worker (que pasa por update_asset_prices,
    # con borrado transaccional) y con el flag full PROPAGADO — es el camino que
    # sostiene la garantía "no se pierde historia si la descarga falla" en la
    # redescarga global. Los demás tests tienen al yahoo dentro del prefetch, así
    # que este else nunca se ejercitaba.
    (aid, ticker), = _seed_assets(n_yf=1)
    events = []
    _patch_cfgs(monkeypatch)

    # prefetch vacío: el yahoo "se cae" del batch (chunk fallido)
    monkeypatch.setattr(
        ps, "_bulk_prefetch_yfinance",
        lambda awd: (events.append(("prefetch", [a.ticker for a, _ in awd])) or {}))
    monkeypatch.setattr(
        ps, "_process_yf_asset_worker",
        lambda *a, **k: (events.append(("yf",)) or (True, None)))

    def fake_other(asset_id, ticker, _dd_cfg=None, _regime_cfg=None,
                   _vol_cfg=None, _sr_cfg=None, skip_indicators=False, full=False):
        events.append(("other", ticker, skip_indicators, full))
        return True, None

    monkeypatch.setattr(ps, "_process_other_asset_worker", fake_other)

    assets = get_session().query(Asset).filter(Asset.id == aid).all()
    out = ps._bulk_download_assets(assets, full=True)

    assert not any(e[0] == "yf" for e in events)          # no usó el worker yf
    assert ("other", ticker, True, True) in events        # fallback con full=True
    assert out == {"total": 1, "success": 1, "errors": []}


# ── Semántica full=True del worker (contra el stub sqlite) ───────────────────

def _df(*dates):
    return pd.DataFrame([
        {"date": d, "open": 1.0, "high": 2.0, "low": 0.5,
         "close": 1.5, "volume": 100}
        for d in dates
    ])


def test_worker_full_reemplaza_la_historia_previa(db):
    (aid, ticker), = _seed_assets(n_yf=1)
    s = get_session()
    s.add(Price(asset_id=aid, date=date(2025, 1, 2), close=1.0))
    s.add(Price(asset_id=aid, date=date(2025, 1, 3), close=2.0))
    s.commit()

    ok, err = ps._process_yf_asset_worker(
        aid, ticker, _df(date(2026, 7, 20)), None,
        None, None, None, None, skip_indicators=True, full=True)

    assert (ok, err) == (True, None)
    s = get_session()
    fechas = [p.date for p in s.query(Price).filter_by(asset_id=aid).all()]
    assert fechas == [date(2026, 7, 20)]           # la historia vieja se fue
    log = s.query(PriceUpdateLog).filter_by(asset_id=aid).first()
    assert log is not None and log.success is True


def test_worker_full_con_descarga_vacia_no_borra_nada(db):
    (aid, ticker), = _seed_assets(n_yf=1)
    s = get_session()
    s.add(Price(asset_id=aid, date=date(2025, 1, 2), close=1.0))
    s.commit()

    ok, err = ps._process_yf_asset_worker(
        aid, ticker, pd.DataFrame(), None,
        None, None, None, None, skip_indicators=True, full=True)

    assert ok is False and ticker in err["ticker"]
    s = get_session()
    fechas = [p.date for p in s.query(Price).filter_by(asset_id=aid).all()]
    assert fechas == [date(2025, 1, 2)]            # intacta: no había datos
    log = s.query(PriceUpdateLog).filter_by(asset_id=aid).first()
    assert log is not None and log.success is False


def test_worker_delta_conserva_la_historia_previa_a_last_date(db):
    # Contraparte de full=True: con full=False + last_date el worker borra SOLO
    # las filas >= last_date (_delete_from_date) y conserva la historia anterior
    # — el camino de la actualización diaria incremental. Sin este test, una
    # regresión que volviera el borrado incondicional dejaría los tests full=True
    # en verde mientras cada delta borraría toda la historia previa a last_date.
    (aid, ticker), = _seed_assets(n_yf=1)
    s = get_session()
    s.add(Price(asset_id=aid, date=date(2025, 1, 2), close=1.0))   # < last_date
    s.add(Price(asset_id=aid, date=date(2025, 6, 2), close=2.0))   # == last_date
    s.commit()

    ok, err = ps._process_yf_asset_worker(
        aid, ticker, _df(date(2025, 6, 2), date(2025, 6, 3)), date(2025, 6, 2),
        None, None, None, None, skip_indicators=True, full=False)

    assert (ok, err) == (True, None)
    s = get_session()
    fechas = sorted(p.date for p in s.query(Price).filter_by(asset_id=aid).all())
    # la previa a last_date sobrevive; solo se reemplazan/agregan las >= last_date
    assert fechas == [date(2025, 1, 2), date(2025, 6, 2), date(2025, 6, 3)]


def test_other_worker_reenvia_full_y_skip_indicators(db, monkeypatch):
    # El worker de otras fuentes/sintéticos delega en update_asset_prices: es el
    # único camino por el que un sintético recibe full=True en la redescarga
    # global. Sin este test, caerse el full=full lo convertiría en un delta
    # (no reconstruye la historia) sin ningún test rojo.
    (aid, ticker), = _seed_assets(n_other=1)
    calls = []
    monkeypatch.setattr(
        ps, "update_asset_prices",
        lambda asset_id, full=False, skip_indicators=False, **k:
            calls.append((asset_id, full, skip_indicators)))

    ok, err = ps._process_other_asset_worker(
        aid, ticker, None, None, None, None, skip_indicators=True, full=True)

    assert (ok, err) == (True, None)
    assert calls == [(aid, True, True)]
