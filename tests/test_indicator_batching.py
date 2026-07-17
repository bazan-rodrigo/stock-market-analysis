"""Pool de backfill por LOTES DE ACTIVOS (fase 1 del plan ProcessPool).

Cubre los contratos nuevos de la inversión de eje (por indicador → por
lotes de activos):
  - _n_batches/_partition_assets: partición balanceada por peso.
  - _resolve_backfill_fn: seam de resolución por código (string), el punto
    donde un proceso hijo — o el módulo futuro de indicadores por
    plantilla — resuelve la función sin recibirla serializada.
  - Orquestación (monkeypatch, patrón test_indicator_pipeline_order): el
    TRUNCATE del force ocurre en el PADRE antes de lanzar workers; la
    consolidación de ind_asset_meta y el __pc__ agregado ocurren DESPUÉS,
    con los conteos/metadatos fusionados entre lotes.
  - Flujo real sobre sqlite: multi-lote ≡ lote único (mismas filas y misma
    ind_asset_meta), delta con camino rápido tras la consolidación del
    padre, y rebuild force con el reset izado.
  - backfill_indicator con asset_ids: scoping real de iteración y de los
    metadatos de benchmark (un lote no re-escribe los metadatos de otros).
"""
from datetime import date, timedelta

import pandas as pd
import sqlalchemy as sa

import app.services.technical_service as ts


# ── Partición ─────────────────────────────────────────────────────────────────

def test_n_batches_respeta_piso_y_techo(monkeypatch):
    monkeypatch.setattr(ts, "_BATCH_FACTOR", 4)
    monkeypatch.setattr(ts, "_MIN_BATCH_ASSETS", 25)
    assert ts._n_batches(0, 4) == 0
    assert ts._n_batches(10, 4) == 1        # menos que el piso: 1 lote
    assert ts._n_batches(100, 4) == 4       # 100//25 = 4 < 16
    assert ts._n_batches(1000, 4) == 16     # techo: workers*4
    assert ts._n_batches(561, 4) == 16


def test_partition_cubre_todo_exactamente_una_vez():
    ids = list(range(1, 12))
    weights = {i: 10 for i in ids}
    batches = ts._partition_assets(ids, weights, 3)
    assert len(batches) == 3
    flat = [a for b in batches for a in b]
    assert sorted(flat) == ids
    sizes = sorted(len(b) for b in batches)
    assert sizes == [3, 4, 4]               # balanceado con pesos uniformes


def test_partition_balancea_por_peso():
    # un activo con historia enorme queda solo en su lote
    weights = {1: 1000, 2: 10, 3: 10, 4: 10, 5: 10}
    batches = ts._partition_assets([1, 2, 3, 4, 5], weights, 2)
    heavy = next(b for b in batches if 1 in b)
    assert heavy == [1]
    other = next(b for b in batches if 1 not in b)
    assert sorted(other) == [2, 3, 4, 5]


def test_partition_es_contigua_por_asset_id():
    # rangos contiguos de asset_id: los vecinos en la PK (asset_id, date)
    # caen en el mismo lote — minimiza gap locks entre workers (ver docstring)
    ids = [5, 1, 9, 3, 7, 2, 8]
    batches = ts._partition_assets(ids, {i: i for i in ids}, 3)
    assert [a for b in batches for a in b] == sorted(ids)
    for prev, nxt in zip(batches, batches[1:]):
        assert max(prev) < min(nxt)


def test_partition_menos_activos_que_lotes_no_deja_vacios():
    batches = ts._partition_assets([7, 9], {7: 1, 9: 1}, 5)
    assert sorted(len(b) for b in batches) == [1, 1]
    assert ts._partition_assets([], {}, 3) == []


def test_partition_es_deterministica():
    ids = list(range(1, 30))
    weights = {i: (i * 37) % 11 for i in ids}
    a = ts._partition_assets(ids, weights, 4)
    b = ts._partition_assets(ids, weights, 4)
    assert a == b


# ── Seam de resolución por código ────────────────────────────────────────────

def test_resolve_backfill_fn_conocido_y_desconocido():
    assert callable(ts._resolve_backfill_fn("return_daily"))
    assert ts._resolve_backfill_fn("no_existe") is None


# ── Orquestación (monkeypatch: solo orden y agregación, sin base) ────────────

class _FakeQuery:
    def __init__(self, items):
        self._items = items

    def filter(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def all(self):
        return self._items


class _FakeSession:
    def __init__(self, defs):
        self._defs = defs

    def query(self, *a, **k):
        return _FakeQuery(self._defs)

    def commit(self):
        pass


class _FakeDef:
    def __init__(self, code):
        self.code = code
        self.last_backfill_seconds = None
        self.last_rebuild_seconds = None


def _stub_orquestacion(monkeypatch, calls, n_assets=3):
    """Stubbea las piezas pesadas y graba el ORDEN de las llamadas."""
    defs = [_FakeDef("return_daily"), _FakeDef("rsi_daily")]
    fake = _FakeSession(defs)
    monkeypatch.setattr(ts, "get_session", lambda: fake)
    monkeypatch.setattr(ts, "_load_all_prices",
                        lambda s: {i: [0] * (10 * i) for i in range(1, n_assets + 1)})
    monkeypatch.setattr(ts, "_resample_ohlc", lambda df, f: None)
    monkeypatch.setattr(ts, "_load_best_sma_cache", lambda s: {})
    monkeypatch.setattr(ts, "_precompute_all_tail_stats", lambda s, c, f: {})
    monkeypatch.setattr(ts, "_MIN_BATCH_ASSETS", 1)   # varios lotes aun con pocos activos

    def _fake_reset(s, codes):
        calls.append(("reset", tuple(codes)))
        return []          # contrato: lista de códigos cuyo reset falló

    monkeypatch.setattr(ts, "_force_reset_ind_tables", _fake_reset)

    def _fake_worker(i, batch, codes, force, tick, *a, **k):
        calls.append(("batch", i, tuple(sorted(batch))))
        per_code = {}
        for code in codes:
            per_code[code] = {
                "inserted": len(batch), "seconds": 1.0,
                "path_counts": {"fast": len(batch), "gap": 0, "checksum": 0,
                                "bench": 0, "empty": 0},
                "slow_asset_ids": {"gap": [], "checksum": [], "bench": [], "empty": []},
                "meta": {"bench_by_asset": None, "checksum_by_asset": None,
                         "stats_by_asset": {aid: (None, None, 1) for aid in batch}},
            }
        return {"batch": i, "inserted": len(batch) * len(codes),
                "per_code": per_code, "errors": []}

    monkeypatch.setattr(ts, "_backfill_batch_worker", _fake_worker)
    monkeypatch.setattr(ts, "_upsert_ind_asset_meta",
                        lambda s, code, **kw: calls.append(("meta", code, kw)))
    monkeypatch.setattr(ts, "_upsert_ind_stats_meta",
                        lambda s, code, stats: calls.append(("stats", code, dict(stats))))


def test_force_trunca_en_el_padre_antes_de_los_lotes(monkeypatch):
    calls: list = []
    _stub_orquestacion(monkeypatch, calls)
    res = ts.backfill_all_indicator_values(force=True)

    kinds = [c[0] for c in calls]
    assert "reset" in kinds
    assert kinds.index("reset") < kinds.index("batch"), \
        "el TRUNCATE debe ocurrir en el padre ANTES de lanzar workers"
    reset = next(c for c in calls if c[0] == "reset")
    assert set(reset[1]) == {"return_daily", "rsi_daily"}
    assert res["errors"] == []
    assert res["success"] == 2


def test_delta_no_trunca(monkeypatch):
    calls: list = []
    _stub_orquestacion(monkeypatch, calls)
    ts.backfill_all_indicator_values(force=False)
    assert all(c[0] != "reset" for c in calls)


def test_consolidacion_despues_de_los_lotes_y_fusionada(monkeypatch):
    calls: list = []
    _stub_orquestacion(monkeypatch, calls, n_assets=3)
    labels: list = []
    ts.backfill_all_indicator_values(progress_cb=lambda c, t, l="": labels.append(l))

    kinds = [c[0] for c in calls]
    last_batch = max(i for i, k in enumerate(kinds) if k == "batch")
    first_stats = kinds.index("stats")
    assert last_batch < first_stats, \
        "la consolidación de ind_asset_meta ocurre tras terminar TODOS los lotes"

    # los stats consolidados traen la unión de los activos de todos los lotes
    stats = next(c for c in calls if c[0] == "stats")
    assert set(stats[2].keys()) == {1, 2, 3}

    # el __pc__ por código sale UNA vez, con los conteos SUMADOS entre lotes
    pcs = [l for l in labels if l.startswith("__pc__:return_daily:")]
    assert pcs == ["__pc__:return_daily:3:0:0:0"]

    # partición: cada activo exactamente una vez entre los lotes
    seen = [a for c in calls if c[0] == "batch" for a in c[2]]
    assert sorted(seen) == [1, 2, 3]


def test_lote_caido_no_rompe_y_marca_los_codigos(monkeypatch):
    calls: list = []
    _stub_orquestacion(monkeypatch, calls)

    def _boom(i, batch, codes, force, tick, *a, **k):
        raise RuntimeError("lote roto")

    monkeypatch.setattr(ts, "_backfill_batch_worker", _boom)
    res = ts.backfill_all_indicator_values(force=False)
    assert res["success"] == 0
    assert res["errors"] and all("lote" in e["code"] for e in res["errors"])


# ── Flujo real sobre sqlite ──────────────────────────────────────────────────

_A1, _A2, _A3, _A4 = 99911, 99912, 99913, 99914
_BENCH = 99910


def _price_df(start: date, n: int, base: float) -> pd.DataFrame:
    rows = [(start + timedelta(days=i), base + i, base + i + 1, base + i - 1)
            for i in range(n)]
    return pd.DataFrame(rows, columns=["date", "close", "high", "low"])


def _seed_assets(s, Asset, Price, ids, days=30):
    caches = {}
    for k, aid in enumerate(ids):
        if s.get(Asset, aid) is None:
            s.add(Asset(id=aid, ticker=f"BT{aid}", name=f"BT{aid}",
                        price_source_id=1))
        df = _price_df(date(2026, 1, 1), days, 100.0 * (k + 1))
        caches[aid] = df
        for _, r in df.iterrows():
            s.add(Price(asset_id=aid, date=r["date"], close=r["close"],
                        high=r["high"], low=r["low"]))
    s.commit()
    return caches


def _cleanup(s, engine, Asset, Price, IndicatorDefinition, code, ids):
    from app.models import indicator_store
    s.rollback()
    s.query(Price).filter(Price.asset_id.in_(ids)).delete(synchronize_session=False)
    s.query(Asset).filter(Asset.id.in_(ids)).delete(synchronize_session=False)
    s.query(IndicatorDefinition).filter(
        IndicatorDefinition.code == code).delete(synchronize_session=False)
    s.execute(sa.text("DELETE FROM ind_asset_meta WHERE code = :c"), {"c": code})
    s.commit()
    with engine.begin() as conn:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS ind_{code}"))
    tbl = indicator_store._meta.tables.get(f"ind_{code}")
    if tbl is not None:
        indicator_store._meta.remove(tbl)


def test_flujo_real_multilote_equivale_a_lote_unico(monkeypatch):
    import app.models  # noqa: F401
    from app.database import Base, Session, engine, get_session
    from app.models import Asset, Price
    from app.models.indicator_definition import IndicatorDefinition
    from app.models.indicator_store import ensure_ind_table, get_ind_table

    Base.metadata.create_all(engine)
    ensure_ind_table("return_daily", "num")
    s = get_session()
    code = "return_daily"
    ids = [_A1, _A2, _A3, _A4]
    try:
        caches = _seed_assets(s, Asset, Price, ids)
        if not s.query(IndicatorDefinition).filter(
                IndicatorDefinition.code == code).first():
            s.add(IndicatorDefinition(code=code, name=code, category="test",
                                      type="num", keep_history=True))
        s.commit()

        # aislar la corrida a este código (otros tests siembran definiciones)
        monkeypatch.setattr(ts, "_BACKFILL_FNS", {code: ts._BACKFILL_FNS[code]})
        monkeypatch.setattr(ts, "_POOL_WORKERS", 1)   # sqlite: un solo escritor

        t = get_ind_table(code)

        def _snapshot():
            rows = s.execute(sa.select(t.c.asset_id, t.c.date, t.c.value)
                             .where(t.c.asset_id.in_(ids))).fetchall()
            meta = s.execute(sa.text(
                "SELECT asset_id, min_date, max_date, row_count"
                " FROM ind_asset_meta WHERE code = :c"), {"c": code}).fetchall()
            return sorted(map(tuple, rows)), sorted(map(tuple, meta))

        def _wipe():
            s.execute(t.delete().where(t.c.asset_id.in_(ids)))
            s.execute(sa.text("DELETE FROM ind_asset_meta WHERE code = :c"),
                      {"c": code})
            s.commit()

        # Corrida A: multi-lote (piso 1 → un lote por activo)
        monkeypatch.setattr(ts, "_MIN_BATCH_ASSETS", 1)
        labels: list = []
        res_a = ts.backfill_all_indicator_values(
            progress_cb=lambda c, tt, l="": labels.append(l),
            price_cache=dict(caches))
        assert res_a["errors"] == []
        assert res_a["inserted"] > 0
        rows_a, meta_a = _snapshot()
        assert len(meta_a) == len(ids), "el padre consolidó stats de todos los lotes"
        assert any(l.startswith("__init__:") for l in labels)
        # el dn por código llegó al total de activos aunque lo avanzaron varios lotes
        ticks = [l for l in labels if l.startswith(f"{code}: ")]
        assert ticks and max(int(l.split(" ")[1].split("/")[0]) for l in ticks) == len(ids)

        # Corrida B: lote único → mismas filas y misma meta
        _wipe()
        monkeypatch.setattr(ts, "_MIN_BATCH_ASSETS", 10_000)
        res_b = ts.backfill_all_indicator_values(price_cache=dict(caches))
        assert res_b["errors"] == []
        rows_b, meta_b = _snapshot()
        assert rows_a == rows_b
        assert meta_a == meta_b

        # Delta sobre B: camino rápido gracias a la meta consolidada —
        # reescribe solo la cola (la última fecha, preliminar) por activo
        monkeypatch.setattr(ts, "_MIN_BATCH_ASSETS", 1)
        labels2: list = []
        res_c = ts.backfill_all_indicator_values(
            progress_cb=lambda c, tt, l="": labels2.append(l),
            price_cache=dict(caches))
        assert res_c["errors"] == []
        assert res_c["inserted"] == len(ids)
        assert f"__pc__:{code}:{len(ids)}:0:0:0" in labels2

        # Rebuild force: reset izado al padre + reconstrucción completa
        res_d = ts.backfill_all_indicator_values(force=True,
                                                 price_cache=dict(caches))
        assert res_d["errors"] == []
        rows_d, meta_d = _snapshot()
        assert rows_d == rows_a
        assert meta_d == meta_a
    finally:
        _cleanup(s, engine, Asset, Price, IndicatorDefinition, code, ids)
        Session.remove()


def test_error_en_un_codigo_no_envenena_el_lote(monkeypatch):
    """Un código que falla dentro de un lote no arrastra a los demás: el
    worker hace rollback y sigue (regresión detectada en revisión — el pool
    viejo aislaba cada código en su propio worker)."""
    import app.models  # noqa: F401
    from sqlalchemy.exc import OperationalError
    from app.database import Base, Session, engine, get_session
    from app.models import Asset, Price
    from app.models.indicator_definition import IndicatorDefinition
    from app.models.indicator_store import ensure_ind_table, get_ind_table

    Base.metadata.create_all(engine)
    ensure_ind_table("rsi_daily", "num")
    ensure_ind_table("return_daily", "num")
    s = get_session()
    ids = [_A1, _A2, _A3, _A4]
    try:
        caches = _seed_assets(s, Asset, Price, ids)
        # rsi_daily primero (empata en _cost_rank, gana por orden de alta)
        for code in ("rsi_daily", "return_daily"):
            if not s.query(IndicatorDefinition).filter(
                    IndicatorDefinition.code == code).first():
                s.add(IndicatorDefinition(code=code, name=code, category="test",
                                          type="num", keep_history=True))
                s.commit()

        def _boom(**kw):
            raise OperationalError("stmt", None, Exception("boom"))

        monkeypatch.setattr(ts, "_BACKFILL_FNS", {
            "rsi_daily": _boom,
            "return_daily": ts._BACKFILL_FNS["return_daily"],
        })
        monkeypatch.setattr(ts, "_POOL_WORKERS", 1)
        monkeypatch.setattr(ts, "_MIN_BATCH_ASSETS", 1)   # varios lotes

        res = ts.backfill_all_indicator_values(price_cache=dict(caches))

        # el código roto falla, el sano completa: 1/2
        assert res["success"] == 1
        # errors deduplicado: UNA entrada para rsi_daily aunque falló en
        # todos los lotes (contrato del pool viejo para el 'X/Y OK')
        rsi_errs = [e for e in res["errors"] if e["code"] == "rsi_daily"]
        assert len(rsi_errs) == 1
        assert "lotes" in rsi_errs[0]["error"]   # anota los lotes afectados
        # return_daily escribió sus filas pese al error previo del lote
        t = get_ind_table("return_daily")
        n_rows = s.execute(sa.select(sa.func.count()).select_from(t)
                           .where(t.c.asset_id.in_(ids))).scalar()
        assert n_rows > 0
        # y su meta quedó consolidada; la del código roto, ausente
        metas = dict(s.execute(sa.text(
            "SELECT code, COUNT(*) FROM ind_asset_meta"
            " WHERE code IN ('rsi_daily','return_daily') GROUP BY code")).fetchall())
        assert metas.get("return_daily") == len(ids)
        assert "rsi_daily" not in metas
    finally:
        _cleanup(s, engine, Asset, Price, IndicatorDefinition, "return_daily", ids)
        _cleanup(s, engine, Asset, Price, IndicatorDefinition, "rsi_daily", ids)
        Session.remove()


def test_backfill_indicator_scopea_lote_y_meta_de_benchmark():
    import app.models  # noqa: F401
    from app.database import Base, Session, engine, get_session
    from app.models import Asset, Price
    from app.models.indicator_definition import IndicatorDefinition
    from app.models.indicator_store import ensure_ind_table, get_ind_table

    Base.metadata.create_all(engine)
    code = "relative_strength_52w"
    ensure_ind_table(code, "num")
    s = get_session()
    ids = [_BENCH, _A1, _A2]
    try:
        caches = _seed_assets(s, Asset, Price, ids, days=25)
        for aid in (_A1, _A2):
            s.get(Asset, aid).benchmark_id = _BENCH
        if not s.query(IndicatorDefinition).filter(
                IndicatorDefinition.code == code).first():
            s.add(IndicatorDefinition(code=code, name=code, category="test",
                                      type="num", keep_history=True))
        s.commit()

        res = ts.backfill_indicator(code, asset_ids=[_A1], defer_meta=True,
                                    price_cache=caches)

        # meta scopeada: SOLO el activo del lote (ni el otro, ni el benchmark)
        assert set(res["meta"]["bench_by_asset"].keys()) == {_A1}
        assert res["meta"]["bench_by_asset"][_A1] == _BENCH
        # no se upserteó nada en ind_asset_meta (defer_meta)
        n_meta = s.execute(sa.text(
            "SELECT COUNT(*) FROM ind_asset_meta WHERE code = :c"),
            {"c": code}).scalar()
        assert n_meta == 0
        # iteración scopeada: sin filas de activos fuera del lote
        t = get_ind_table(code)
        others = s.execute(sa.select(sa.func.count()).select_from(t)
                           .where(t.c.asset_id.in_([_A2, _BENCH]))).scalar()
        assert others == 0
    finally:
        _cleanup(s, engine, Asset, Price, IndicatorDefinition, code, ids)
        Session.remove()
