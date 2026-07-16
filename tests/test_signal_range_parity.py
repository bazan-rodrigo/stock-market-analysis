"""Paridad modo rango vs camino por-fecha del backfill de señales.

signal_backfill_range hace el mismo cálculo que el loop por-fecha
(group_score_service.run_daily → compute_signal_values →
compute_group_signal_values → compute_all_strategies) pero con barrido
cronológico y escrituras en bloque. Este test corre AMBOS caminos sobre el
mismo dataset sintético en el sqlite stub y exige igualdad exacta de
signal_value, group_signal_value, group_scores y strategy_result.

Cubre: as-of con huecos (tendencias semanales), tope de 45 días, valores
NULL, threshold/discrete_map/range, señal de grupo, indicador
virtual last_close, y estrategia con filtro (indicador as-of + operando
señal) — los caminos por donde ya hubo bugs reales de semántica.
"""
import json
from datetime import date, timedelta

import pytest
import sqlalchemy as sa

from app.database import Base, engine, get_session

_TREND_TABLES = ("ind_trend_daily", "ind_trend_weekly", "ind_trend_monthly")
_NUM_TABLE    = "ind_zz_par_rsi"
_ALL_IND      = _TREND_TABLES + (_NUM_TABLE,)

_DERIVED = ("signal_value", "group_signal_value", "group_scores",
            "strategy_result", "signal_eval_log")
_SEEDED  = ("prices", "strategy_component", "strategy", "`signal`",
            "indicator_definitions", "assets")

_START = date(2026, 1, 5)   # lunes
_N_DATES = 40               # > _RANGE_MODE_MIN_DATES: el rango es el camino real


def _trading_dates():
    out, d = [], _START
    while len(out) < _N_DATES:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


@pytest.fixture()
def pipeline_db():
    import app.models  # noqa: F401 — registra todos los modelos en Base.metadata
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        for t in _ALL_IND:
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {t}"))
            # Mismos tipos que la migración 0043: FLOAT para indicadores
            # numéricos, VARCHAR para categóricos
            vtype = "FLOAT" if t == _NUM_TABLE else "VARCHAR(30)"
            conn.execute(sa.text(
                f"CREATE TABLE {t} ("
                "  asset_id INTEGER NOT NULL,"
                "  date DATE NOT NULL,"
                f"  value {vtype},"
                "  PRIMARY KEY (asset_id, date))"
            ))
        for t in _DERIVED + _SEEDED:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    yield
    with engine.begin() as conn:
        for t in _ALL_IND:
            conn.execute(sa.text(f"DROP TABLE IF EXISTS {t}"))
        for t in _DERIVED + _SEEDED:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    from app.models import indicator_store as _mod
    for t in _ALL_IND:
        if t in _mod._meta.tables:
            _mod._meta.remove(_mod._meta.tables[t])
    get_session().rollback()


def _seed(dates):
    from app.models import (Asset, Price, SignalDefinition, Strategy,
                            StrategyComponent)
    from app.models.indicator_definition import IndicatorDefinition
    from app.models.indicator_store import get_ind_table

    s = get_session()

    for code, typ in (("trend_daily", "str"), ("trend_weekly", "str"),
                      ("trend_monthly", "str"), ("zz_par_rsi", "num")):
        s.add(IndicatorDefinition(code=code, name=code, category="test",
                                  type=typ, keep_history=True))

    # 3 activos: dos del sector 1, uno del sector 2; el 3 con datos ralos
    for i, sector in ((1, 1), (2, 1), (3, 2)):
        s.add(Asset(id=i, ticker=f"T{i}", name=f"Test {i}", sector_id=sector,
                    market_id=1, price_source_id=1))
    s.flush()

    for n, d in enumerate(dates):
        for aid in (1, 2, 3):
            if aid == 3 and n % 3:      # activo 3: cotiza 1 de cada 3 ruedas
                continue
            base = 10.0 * aid + n * 0.1
            s.add(Price(asset_id=aid, date=d, open=base, high=base + 1,
                        low=base - 1, close=base + 0.5, volume=1000))

    signals = [
        # threshold numérico sobre ind_zz_par_rsi
        dict(key="par_rsi", name="RSI par", source="asset",
             indicator_key="zz_par_rsi", formula_type="threshold",
             params={"thresholds": [[70, -100], [30, 0], [None, 100]]}),
        # discrete_map sobre tendencia diaria
        dict(key="par_trend", name="Trend par", source="asset",
             indicator_key="trend_daily", formula_type="discrete_map",
             params={"map": {"bullish": 80, "bearish": -80, "lateral": 0}}),
        # range sobre el virtual last_close
        dict(key="par_close", name="Close par", source="asset",
             indicator_key="last_close", formula_type="range",
             params={"min": 10, "max": 35}),
        # señal de grupo sobre el score sectorial diario
        dict(key="par_sector", name="Sector par", source="group",
             group_type="sector", indicator_key="regime_score_d",
             formula_type="range", params={"min": -100, "max": 100}),
    ]
    ids = {}
    for spec in signals:
        sig = SignalDefinition(
            key=spec["key"], name=spec["name"], source=spec["source"],
            group_type=spec.get("group_type"),
            indicator_key=spec.get("indicator_key"),
            formula_type=spec["formula_type"],
            params=json.dumps(spec["params"]), is_public=True)
        s.add(sig)
        s.flush()
        ids[spec["key"]] = sig.id

    # Estrategia con filtro: tendencia as-of alcista Y score de par_rsi > -50
    tree = {"op": "AND", "children": [
        {"cond": {"left": {"type": "indicator", "key": "trend_daily"},
                  "operator": "in",
                  "right": {"type": "const", "value": ["bullish", "lateral"]},
                  "resolution": "historic"}},
        {"cond": {"left": {"type": "signal", "key": "par_rsi"},
                  "operator": ">",
                  "right": {"type": "const", "value": -50}}},
    ]}
    strat = Strategy(name="Paridad", is_public=True,
                     filter_conditions=json.dumps(tree))
    s.add(strat)
    s.flush()
    s.add(StrategyComponent(strategy_id=strat.id, signal_id=ids["par_trend"],
                            weight=2.0))
    s.add(StrategyComponent(strategy_id=strat.id, signal_id=ids["par_sector"],
                            weight=1.0, scope="own_group", group_type="sector"))
    s.commit()

    # Indicadores: diario denso (con NULLs y regímenes variados), semanal/
    # mensual ralo (ejercita el as-of), numérico con huecos para el activo 3
    trend_cycle = ["bullish", "bullish", "lateral", "bearish", "bullish"]
    t_rows, w_rows, m_rows, n_rows = [], [], [], []
    for n, d in enumerate(dates):
        for aid in (1, 2, 3):
            if aid == 3 and n % 3:
                continue
            t_rows.append({"asset_id": aid, "date": d,
                           "value": None if (aid == 2 and n % 7 == 5)
                           else trend_cycle[(n + aid) % 5]})
            n_rows.append({"asset_id": aid, "date": d,
                           "value": float(20 + ((n * 7 + aid * 13) % 60))})
        if d.weekday() == 4:            # viernes: etiqueta semanal
            for aid in (1, 2):
                w_rows.append({"asset_id": aid, "date": d,
                               "value": trend_cycle[(n // 5 + aid) % 5]})
        if n % 21 == 20:                # etiqueta mensual
            for aid in (1, 2):
                m_rows.append({"asset_id": aid, "date": d,
                               "value": trend_cycle[(n // 21 + aid) % 5]})

    with engine.begin() as conn:
        conn.execute(get_ind_table("trend_daily").insert(), t_rows)
        if w_rows:
            conn.execute(get_ind_table("trend_weekly").insert(), w_rows)
        if m_rows:
            conn.execute(get_ind_table("trend_monthly").insert(), m_rows)
        conn.execute(get_ind_table("zz_par_rsi").insert(), n_rows)


def _snapshot():
    s = get_session()
    out = {}
    out["sv"] = sorted(
        (r.signal_id, r.asset_id, str(r.date), round(r.score, 6))
        for r in s.execute(sa.text(
            "SELECT signal_id, asset_id, date, score FROM signal_value")))
    out["gsv"] = sorted(
        (r.signal_id, r.group_type, r.group_id, str(r.date), round(r.score, 6))
        for r in s.execute(sa.text(
            "SELECT signal_id, group_type, group_id, date, score"
            " FROM group_signal_value")))
    out["gs"] = sorted(
        (r.group_type, r.group_id, str(r.date),
         None if r.regime_score_d is None else round(r.regime_score_d, 6),
         None if r.regime_score_w is None else round(r.regime_score_w, 6),
         None if r.regime_score_m is None else round(r.regime_score_m, 6),
         r.n_assets)
        for r in s.execute(sa.text(
            "SELECT group_type, group_id, date, regime_score_d,"
            " regime_score_w, regime_score_m, n_assets FROM group_scores")))
    out["sr"] = sorted(
        (r.strategy_id, r.asset_id, str(r.date), round(r.score, 6),
         round(r.pct, 6))
        for r in s.execute(sa.text(
            "SELECT strategy_id, asset_id, date, score, pct "
            "FROM strategy_result")))
    return out


def _wipe_derived():
    with engine.begin() as conn:
        for t in _DERIVED:
            conn.execute(sa.text(f"DELETE FROM {t}"))


def _assert_range_parity(ranged, reference, last_str):
    """El modo rango reproduce EXACTO signal_value/group_signal_value/
    strategy_result. group_scores diverge a propósito: escribe los tipos que
    alguna estrategia consume (acá 'sector') en toda la historia, y todos los
    tipos solo en la última fecha (mapa de mercado). El camino por-fecha, en
    cambio, escribe todos los tipos todas las fechas. Ver
    signal_backfill_range._derive_needed_groups."""
    assert ranged["sv"]  == reference["sv"]
    assert ranged["gsv"] == reference["gsv"]
    assert ranged["sr"]  == reference["sr"]
    expected_gs = sorted(row for row in reference["gs"]
                         if row[0] == "sector" or row[2] == last_str)
    assert ranged["gs"] == expected_gs


def test_paridad_rango_vs_por_fecha(pipeline_db):
    from app.services import (group_score_service, signal_backfill_range,
                              signal_service, strategy_service)

    dates = _trading_dates()
    _seed(dates)
    last = dates[-1]

    # ── Camino por-fecha (referencia) ─────────────────────────────────────
    for d in dates:
        group_score_service.run_daily(d)
        signal_service.compute_signal_values(d, latest_price_date=last)
        signal_service.compute_group_signal_values(d)
        strategy_service.compute_all_strategies(d)
    reference = _snapshot()

    # Sanity: el dataset produce datos reales en las cuatro tablas
    assert reference["sv"] and reference["gsv"]
    assert reference["gs"] and reference["sr"]

    # ── Modo rango sobre base limpia ──────────────────────────────────────
    _wipe_derived()
    result = signal_backfill_range.run_range(
        dates, only_ids=None, strategy_id=None, scope_kind=None,
        latest_price_date=last, eval_kind="all", eval_ref=0, logged=set())

    assert result["errors"] == []
    assert result["success"] == len(dates)

    ranged = _snapshot()
    _assert_range_parity(ranged, reference, str(dates[-1]))

    # El modo rango además registra TODAS las fechas como evaluadas
    s = get_session()
    marked = {str(r.date) for r in s.execute(sa.text(
        "SELECT date FROM signal_eval_log WHERE scope_kind='all' AND ref_id=0"))}
    assert marked == {str(d) for d in dates}


def test_strategy_only_lee_senales_y_reproduce_strategy_result(pipeline_db):
    """with_signals=False (modo strategy_only, elegido por el usuario cuando
    no cambiaron señales/indicadores): las señales se LEEN de las tablas en
    vez de re-evaluarse y solo se reconstruye strategy_result — el resultado
    debe ser IDÉNTICO al pipeline completo, y las tablas de señales/grupos
    no deben modificarse."""
    from app.models import Strategy
    from app.services import (group_score_service, signal_service,
                              strategy_service)

    dates = _trading_dates()
    _seed(dates)
    last = dates[-1]

    for d in dates:
        group_score_service.run_daily(d)
        signal_service.compute_signal_values(d, latest_price_date=last)
        signal_service.compute_group_signal_values(d)
        strategy_service.compute_all_strategies(d)
    reference = _snapshot()
    assert reference["sr"]

    s = get_session()
    sid = s.query(Strategy).one().id

    # Se borra SOLO strategy_result; el modo strategy_only debe
    # reconstruirlo leyendo las señales guardadas (end-to-end real:
    # rebuild_signal_history resuelve alcance y entra al modo rango)
    with engine.begin() as conn:
        conn.execute(sa.text("DELETE FROM strategy_result"))
    result = signal_service.rebuild_signal_history(
        scope=f"strategy:{sid}", with_signals=False)
    assert result["errors"] == []

    after = _snapshot()
    assert after["sr"] == reference["sr"]     # idéntico al pipeline completo
    assert after["sv"] == reference["sv"]     # señales INTACTAS
    assert after["gsv"] == reference["gsv"]
    assert after["gs"] == reference["gs"]


def test_rango_respeta_chunks_chicos(pipeline_db, monkeypatch):
    """El corte en chunks no puede cambiar el resultado (el as-of de los
    primeros días de un chunk depende de la ventana de 45 días previa)."""
    from app.services import (group_score_service, signal_backfill_range,
                              signal_service, strategy_service)

    dates = _trading_dates()
    _seed(dates)
    last = dates[-1]

    for d in dates:
        group_score_service.run_daily(d)
        signal_service.compute_signal_values(d, latest_price_date=last)
        signal_service.compute_group_signal_values(d)
        strategy_service.compute_all_strategies(d)
    reference = _snapshot()

    _wipe_derived()
    monkeypatch.setattr(signal_backfill_range, "_CHUNK_DATES", 7)
    # Flush intermedio cada pocas filas: el corte por volumen dentro del
    # chunk tampoco puede cambiar el resultado
    monkeypatch.setattr(signal_backfill_range, "_MAX_ROWS_PER_FLUSH", 40)
    result = signal_backfill_range.run_range(
        dates, only_ids=None, strategy_id=None, scope_kind=None,
        latest_price_date=last, eval_kind="all", eval_ref=0, logged=set())

    assert result["errors"] == []
    _assert_range_parity(_snapshot(), reference, str(dates[-1]))

    # Rebuild (force + full_wipe) SOBRE tablas ya pobladas — el caso real:
    # la limpieza única al inicio + batches solo-INSERT deben reproducir
    # exactamente el mismo estado, sin duplicados
    result = signal_backfill_range.run_range(
        dates, only_ids=None, strategy_id=None, scope_kind=None,
        latest_price_date=last, eval_kind="all", eval_ref=0,
        logged={d for d in dates}, force=True, full_wipe=True)

    assert result["errors"] == []
    _assert_range_parity(_snapshot(), reference, str(dates[-1]))


def _seed_sin_grupo(dates):
    """Igual que _seed pero SIN ninguna señal de grupo ni scope de grupo: es
    la situación real del usuario (fuente=grupo no usada). group_scores no
    debería escribir historia."""
    from app.models import (Asset, Price, SignalDefinition, Strategy,
                            StrategyComponent)
    from app.models.indicator_definition import IndicatorDefinition
    from app.models.indicator_store import get_ind_table

    s = get_session()
    s.add(IndicatorDefinition(code="trend_daily", name="trend_daily",
                              category="test", type="str", keep_history=True))
    for i, sector in ((1, 1), (2, 2)):
        s.add(Asset(id=i, ticker=f"T{i}", name=f"Test {i}", sector_id=sector,
                    market_id=1, price_source_id=1))
    s.flush()
    for n, d in enumerate(dates):
        for aid in (1, 2):
            base = 10.0 * aid + n * 0.1
            s.add(Price(asset_id=aid, date=d, open=base, high=base + 1,
                        low=base - 1, close=base + 0.5, volume=1000))
    sig = SignalDefinition(key="trend_a", name="Trend", source="asset",
                           indicator_key="trend_daily", formula_type="discrete_map",
                           params=json.dumps({"map": {"bullish": 80, "bearish": -80,
                                                      "lateral": 0}}), is_public=True)
    s.add(sig)
    s.flush()
    strat = Strategy(name="SoloActivo", is_public=True, filter_conditions=None)
    s.add(strat)
    s.flush()
    s.add(StrategyComponent(strategy_id=strat.id, signal_id=sig.id, weight=1.0))
    s.commit()

    cycle = ["bullish", "lateral", "bearish", "bullish", "lateral"]
    rows = [{"asset_id": aid, "date": d, "value": cycle[(n + aid) % 5]}
            for n, d in enumerate(dates) for aid in (1, 2)]
    with engine.begin() as conn:
        conn.execute(get_ind_table("trend_daily").insert(), rows)


def test_sin_senales_de_grupo_no_escribe_historia_group_scores(pipeline_db):
    """El bug que motivó el cambio: sin señales de grupo, el modo rango
    escribía la agregación de todos los grupos por cada fecha aunque nadie la
    leyera. Ahora group_scores solo lleva la última fecha (mapa de mercado)."""
    from app.services import signal_backfill_range

    dates = _trading_dates()
    _seed_sin_grupo(dates)
    last = dates[-1]

    result = signal_backfill_range.run_range(
        dates, only_ids=None, strategy_id=None, scope_kind=None,
        latest_price_date=last, eval_kind="all", eval_ref=0, logged=set())
    assert result["errors"] == []

    snap = _snapshot()
    assert snap["sv"] and snap["sr"]        # las señales/estrategias sí corren
    assert snap["gsv"] == []                # sin señales de grupo, nada acá
    # group_scores: SOLO la última fecha (para el mapa de mercado)
    gs_dates = {row[2] for row in snap["gs"]}
    assert gs_dates == {str(last)}


def _seed_sector_restringido(dates):
    """Señal de grupo por sector + estrategia que la usa (own_group) pero con
    filtro `sector = 1`. Solo el sector 1 debería calcularse."""
    from app.models import (Asset, Price, SignalDefinition, Strategy,
                            StrategyComponent)
    from app.models.indicator_definition import IndicatorDefinition
    from app.models.indicator_store import get_ind_table

    s = get_session()
    s.add(IndicatorDefinition(code="trend_daily", name="trend_daily",
                              category="test", type="str", keep_history=True))
    # sectores 1 y 2; el filtro dejará pasar solo el 1
    for i, sector in ((1, 1), (2, 1), (3, 2)):
        s.add(Asset(id=i, ticker=f"T{i}", name=f"Test {i}", sector_id=sector,
                    market_id=1, price_source_id=1))
    s.flush()
    for n, d in enumerate(dates):
        for aid in (1, 2, 3):
            base = 10.0 * aid + n * 0.1
            s.add(Price(asset_id=aid, date=d, open=base, high=base + 1,
                        low=base - 1, close=base + 0.5, volume=1000))
    sig = SignalDefinition(key="sector_trend", name="Sector", source="group",
                           group_type="sector", indicator_key="regime_score_d",
                           formula_type="range",
                           params=json.dumps({"min": -100, "max": 100}),
                           is_public=True)
    s.add(sig)
    s.flush()
    tree = {"cond": {"left": {"type": "attribute", "key": "sector"},
                     "operator": "=", "right": {"type": "const", "value": 1}}}
    strat = Strategy(name="SoloSector1", is_public=True,
                     filter_conditions=json.dumps(tree))
    s.add(strat)
    s.flush()
    s.add(StrategyComponent(strategy_id=strat.id, signal_id=sig.id, weight=1.0,
                            scope="own_group", group_type="sector"))
    s.commit()

    cycle = ["bullish", "lateral", "bearish", "bullish", "lateral"]
    rows = [{"asset_id": aid, "date": d, "value": cycle[(n + aid) % 5]}
            for n, d in enumerate(dates) for aid in (1, 2, 3)]
    with engine.begin() as conn:
        conn.execute(get_ind_table("trend_daily").insert(), rows)
    return sig.id


def test_senal_de_grupo_restringida_al_sector_del_filtro(pipeline_db):
    """El pedido del usuario: si la estrategia filtra a un grupo, la señal de
    grupo solo se calcula para ESE grupo. Y 'Calcular historia' sobre la señal
    respeta el filtro de las estrategias que la usan (no calcula todos)."""
    from app.services import signal_backfill_range

    dates = _trading_dates()
    _seed_sector_restringido(dates)
    last = dates[-1]

    # ── Corrida global ────────────────────────────────────────────────────
    _wipe_derived()
    res = signal_backfill_range.run_range(
        dates, only_ids=None, strategy_id=None, scope_kind=None,
        latest_price_date=last, eval_kind="all", eval_ref=0, logged=set())
    assert res["errors"] == []

    gsv = _snapshot()["gsv"]
    assert gsv, "la señal de grupo debe puntuar en el sector filtrado"
    assert {row[2] for row in gsv} == {1}, "solo el sector 1 (el del filtro)"

    # group_scores histórico (fechas != última) solo sector 1; la última va
    # completa (sector 1 y 2) para el mapa de mercado
    for gt, gid, d, *_ in _snapshot()["gs"]:
        if d != str(last):
            assert (gt, gid) == ("sector", 1)

    # ── 'Calcular historia' sobre la señal: DEBE respetar el filtro ────────
    # (antes calculaba todos los sectores; la corrección deriva de la estrategia)
    from app.services import signal_service
    only_ids, _sid, _ = signal_service._scope_signal_ids(
        get_session(), "signal:sector_trend")
    _wipe_derived()
    res = signal_backfill_range.run_range(
        dates, only_ids=only_ids, strategy_id=None, scope_kind="signal",
        latest_price_date=last, eval_kind="signal", eval_ref=0, logged=set())
    assert res["errors"] == []
    assert {row[2] for row in _snapshot()["gsv"]} == {1}, \
        "el alcance de señal también se limita al sector 1 del filtro"


def _seed_dos_tipos(dates):
    """Dos señales de grupo de tipos distintos (sector y market), cada una con
    su estrategia. Sirve para verificar que recalcular una NO borra la historia
    de la otra."""
    from app.models import (Asset, Price, SignalDefinition, Strategy,
                            StrategyComponent)
    from app.models.indicator_definition import IndicatorDefinition
    from app.models.indicator_store import get_ind_table

    s = get_session()
    s.add(IndicatorDefinition(code="trend_daily", name="trend_daily",
                              category="test", type="str", keep_history=True))
    for i, sector, market in ((1, 1, 1), (2, 2, 1), (3, 1, 2)):
        s.add(Asset(id=i, ticker=f"T{i}", name=f"Test {i}", sector_id=sector,
                    market_id=market, price_source_id=1))
    s.flush()
    for n, d in enumerate(dates):
        for aid in (1, 2, 3):
            base = 10.0 * aid + n * 0.1
            s.add(Price(asset_id=aid, date=d, open=base, high=base + 1,
                        low=base - 1, close=base + 0.5, volume=1000))
    ids = {}
    for key, gtype in (("sector_sig", "sector"), ("market_sig", "market")):
        sig = SignalDefinition(key=key, name=key, source="group",
                               group_type=gtype, indicator_key="regime_score_d",
                               formula_type="range",
                               params=json.dumps({"min": -100, "max": 100}),
                               is_public=True)
        s.add(sig)
        s.flush()
        ids[key] = sig.id
        strat = Strategy(name=f"E-{gtype}", is_public=True, filter_conditions=None)
        s.add(strat)
        s.flush()
        s.add(StrategyComponent(strategy_id=strat.id, signal_id=sig.id,
                                weight=1.0, scope="own_group", group_type=gtype))
    s.commit()

    cycle = ["bullish", "lateral", "bearish", "bullish", "lateral"]
    rows = [{"asset_id": aid, "date": d, "value": cycle[(n + aid) % 5]}
            for n, d in enumerate(dates) for aid in (1, 2, 3)]
    with engine.begin() as conn:
        conn.execute(get_ind_table("trend_daily").insert(), rows)
    return ids


def test_rebuild_acotado_no_borra_historia_de_otro_tipo(pipeline_db):
    """Un rebuild con alcance de una señal (sector) NO debe borrar la historia
    de group_scores de otro tipo (market) que otra señal necesita. El DELETE de
    group_scores está acotado a los tipos que la corrida reescribe."""
    from app.services import signal_backfill_range, signal_service

    dates = _trading_dates()
    _seed_dos_tipos(dates)
    last = dates[-1]

    # Global: escribe historia de sector Y market
    res = signal_backfill_range.run_range(
        dates, only_ids=None, strategy_id=None, scope_kind=None,
        latest_price_date=last, eval_kind="all", eval_ref=0, logged=set())
    assert res["errors"] == []
    market_hist_antes = sorted(row for row in _snapshot()["gs"]
                               if row[0] == "market" and row[2] != str(last))
    assert market_hist_antes, "el seed debe producir historia de market"

    # Rebuild (force) acotado a la señal de sector
    only_ids, _sid, _ = signal_service._scope_signal_ids(
        get_session(), "signal:sector_sig")
    res = signal_backfill_range.run_range(
        dates, only_ids=only_ids, strategy_id=None, scope_kind="signal",
        latest_price_date=last, eval_kind="signal", eval_ref=0,
        logged={d for d in dates}, force=True)
    assert res["errors"] == []

    market_hist_despues = sorted(row for row in _snapshot()["gs"]
                                 if row[0] == "market" and row[2] != str(last))
    assert market_hist_despues == market_hist_antes, \
        "el rebuild de la señal de sector no debe tocar la historia de market"
