"""
Modo rango del backfill de señales/estrategias.

El pipeline por-fecha (signal_service.run_daily y compañía) está diseñado
para UNA fecha — el uso diario del scheduler. Llamarlo 25.000 veces en un
loop repite por fecha queries que son constantes (definiciones, grupos de
activos) o incrementales (as-of de indicadores). Este módulo hace el mismo
cálculo para un RANGO de fechas con:

- Contexto invariante cargado una vez (señales parseadas, grupos de
  activos, estrategias con filtros parseados, valores current).
- Barrido cronológico por chunks: cada tabla ind_* se carga UNA vez por
  chunk (ventana [inicio - 45 días, fin]) ordenada por fecha, y un puntero
  por código avanza fecha a fecha — el as-of sale de memoria en O(1)
  amortizado, con la MISMA semántica que query_values_asof (última fila
  <= fecha, tope 45 días, valores NULL excluidos).
- Escrituras en bloque por chunk: DELETE de las fechas procesadas (acotado
  al alcance) + INSERT masivo, un commit por chunk.

La MATEMÁTICA no vive acá: los evaluadores compartidos
(_evaluate_asset_signal_scores, _evaluate_group_signal_scores,
aggregate_group_scores, rank_strategy_assets) son los mismos que usa el
camino por-fecha — ver tests/test_signal_range_parity.py.

Divergencia deliberada con el camino por-fecha: el DELETE por fecha
elimina filas obsoletas (señales/grupos que ya no puntúan ese día) que el
upsert por-fecha dejaría zombies. Es una mejora, no una regresión.
"""
import logging
from datetime import timedelta
from types import SimpleNamespace

import sqlalchemy as sa

from app.database import get_session
from app.models import (
    Asset,
    GroupScore,
    GroupSignalValue,
    SignalEvalLog,
    SignalValue,
    Strategy,
    StrategyResult,
)
from app.models.indicator_store import (
    ASOF_MAX_LOOKBACK_DAYS,
    CurrentIndicatorValue,
    get_ind_table,
)
from app.models.price import Price
from app.services import strategy_filter
from app.services.group_score_service import (
    _TF_MAP,
    _TREND_CODES,
    aggregate_group_scores,
)
from app.services.signal_service import (
    _VIRTUAL_CODES,
    _evaluate_asset_signal_scores,
    _evaluate_group_signal_scores,
    _prepare_signals,
)
from app.services.strategy_service import rank_strategy_assets

logger = logging.getLogger(__name__)

_CHUNK_DATES = 250   # ~1 año de ruedas por chunk (acota memoria y transacción)


class _Sweep:
    """Puntero cronológico sobre las filas (asset_id, date, value) de un
    ind_{code}, ordenadas por fecha. advance(d) deja en .live la última
    fila <= d por activo."""

    __slots__ = ("rows", "idx", "live")

    def __init__(self, rows):
        self.rows = rows      # [(asset_id, date, value)] orden por date
        self.idx  = 0
        self.live = {}        # {asset_id: (date, value)}

    def advance(self, d):
        rows, n = self.rows, len(self.rows)
        i = self.idx
        while i < n and rows[i][1] <= d:
            self.live[rows[i][0]] = (rows[i][1], rows[i][2])
            i += 1
        self.idx = i

    def snapshot_asof(self, d):
        """{asset_id: value} con la semántica exacta de query_values_asof:
        última fila <= d, no más vieja que 45 días, valor no NULL."""
        cutoff = d - timedelta(days=ASOF_MAX_LOOKBACK_DAYS)
        return {aid: v for aid, (dt, v) in self.live.items()
                if v is not None and dt >= cutoff}

    def exact(self, d):
        """{asset_id: value} solo de filas con fecha EXACTA d (semántica de
        compute_group_scores sobre ind_trend_*)."""
        return {aid: v for aid, (dt, v) in self.live.items() if dt == d}


def _load_sweep(s, code, window_start, window_end) -> _Sweep:
    try:
        tbl = get_ind_table(code)
    except sa.exc.NoSuchTableError:
        logger.warning("signal_backfill_range: tabla ind_%s no existe", code)
        return _Sweep([])
    rows = s.execute(
        sa.select(tbl.c.asset_id, tbl.c.date, tbl.c.value)
        .where(tbl.c.date >= window_start, tbl.c.date <= window_end)
        .order_by(tbl.c.date)
    ).fetchall()
    return _Sweep([(r[0], r[1], r[2]) for r in rows])


def _load_current_values(s, codes) -> dict[str, dict]:
    """{code: {asset_id: value}} desde current_indicator_values (indicadores
    sin historia y operandos resolution=current del filtro)."""
    if not codes:
        return {}
    out: dict[str, dict] = {c: {} for c in codes}
    rows = s.query(
        CurrentIndicatorValue.asset_id, CurrentIndicatorValue.code,
        CurrentIndicatorValue.value_num, CurrentIndicatorValue.value_str,
    ).filter(CurrentIndicatorValue.code.in_(list(codes))).all()
    for aid, code, num, txt in rows:
        value = num if num is not None else txt
        if value is not None:
            out[code][aid] = value
    return out


def run_range(dates, *, only_ids, strategy_id, scope_kind,
              latest_price_date, eval_kind, eval_ref, logged,
              progress_cb=None) -> dict:
    """Equivalente en rango del loop por-fecha de _signal_history_run.
    dates: lista ordenada de fechas a procesar (huecos + última)."""
    s = get_session()

    # ── Contexto invariante de la corrida ─────────────────────────────────
    prep = _prepare_signals(s, only_ids)
    if prep is None:
        return {"total": 0, "success": 0, "errors": []}

    asset_groups = {
        a.id: {
            "sector":          a.sector_id,
            "market":          a.market_id,
            "industry":        a.industry_id,
            "country":         a.country_id,
            "instrument_type": a.instrument_type_id,
        }
        for a in s.query(
            Asset.id, Asset.sector_id, Asset.market_id,
            Asset.industry_id, Asset.country_id, Asset.instrument_type_id,
        ).all()
    }
    asset_meta = asset_groups  # mismo mapa que usa compute_group_scores

    # Estrategias a calcular (con filtro parseado y operandos clasificados)
    if scope_kind == "strategy":
        strategies = s.query(Strategy).filter(Strategy.id == strategy_id).all()
    elif scope_kind is None:
        strategies = s.query(Strategy).all()
    else:  # scope señal: no toca resultados de estrategias
        strategies = []

    strat_ctx = []
    filter_hist_codes: set[str] = set()
    filter_current_codes: set[str] = set()
    filter_signal_keys: set[str] = set()
    for strat in strategies:
        if not strat.components:
            continue
        tree = strategy_filter.parse_tree(strat.filter_conditions)
        operands = strategy_filter.collect_operands(tree) if tree is not None else set()
        for t, key, res in operands:
            if t == "indicator" and res == "current":
                filter_current_codes.add(key)
            elif t == "indicator":
                filter_hist_codes.add(key)
            elif t == "signal":
                filter_signal_keys.add(key)
        strat_ctx.append({
            "id": strat.id,
            "components": list(strat.components),
            "signal_ids": {c.signal_id for c in strat.components},
            "tree": tree,
            "operands": operands,
        })

    sig_id_by_key = {sig.key: sig.id for sig in prep["signals"]}

    # Códigos a barrer: señales + tendencias de grupo + filtro (historic)
    sweep_codes = (set(prep["hist_codes"]) | set(_TREND_CODES)
                   | filter_hist_codes)

    # Valores current (una vez: son el estado VIGENTE, no dependen de la fecha)
    current_by_code = _load_current_values(
        s, set(prep["nohist_codes"]) | filter_current_codes)

    need_last_close = "last_close" in prep["virtual_codes"]

    signal_ids_all  = [sig.id for sig in prep["signals"]]
    group_sig_ids   = [sig.id for sig in prep["group_signals"]]
    strat_ids       = [c["id"] for c in strat_ctx]

    total, ok = len(dates), 0
    errors: list[dict] = []
    done = 0

    # ── Chunks ────────────────────────────────────────────────────────────
    for start in range(0, total, _CHUNK_DATES):
        chunk = dates[start:start + _CHUNK_DATES]
        window_start = chunk[0] - timedelta(days=ASOF_MAX_LOOKBACK_DAYS)
        window_end   = chunk[-1]

        try:
            sweeps = {code: _load_sweep(s, code, window_start, window_end)
                      for code in sweep_codes}

            closes_by_date: dict = {}
            if need_last_close:
                rows = s.query(Price.date, Price.asset_id, Price.close).filter(
                    Price.date >= chunk[0], Price.date <= window_end).all()
                for dt, aid, close in rows:
                    if close is not None:
                        closes_by_date.setdefault(dt, {})[aid] = float(close)

            sv_rows, gsv_rows, gs_rows, sr_rows, marker_rows = [], [], [], [], []

            for d in chunk:
                done += 1
                if progress_cb:
                    progress_cb(done, total, str(d))

                for sw in sweeps.values():
                    sw.advance(d)

                # Scores de grupo (tendencias con fecha EXACTA d)
                asset_trends: dict[int, dict] = {}
                for code in _TREND_CODES:
                    tf = _TF_MAP[code]
                    for aid, val in sweeps[code].exact(d).items():
                        asset_trends.setdefault(aid, {})[tf] = val
                aggregated = aggregate_group_scores(asset_trends, asset_meta)
                gscores = {
                    key: SimpleNamespace(group_type=key[0], group_id=key[1], **vals)
                    for key, vals in aggregated.items()
                }
                gs_rows.extend(
                    {"group_type": gt, "group_id": gid, "date": d, **vals}
                    for (gt, gid), vals in aggregated.items()
                )

                # Snapshots as-of de todos los códigos barridos
                snap = {code: sw.snapshot_asof(d) for code, sw in sweeps.items()}

                # isnaps para señales de activo (hist + current-si-es-hoy + virtual)
                isnaps: dict[int, dict] = {}
                for code in prep["hist_codes"]:
                    for aid, val in snap.get(code, {}).items():
                        isnaps.setdefault(aid, {})[code] = val
                if prep["nohist_codes"] and d == latest_price_date:
                    for code in prep["nohist_codes"]:
                        for aid, val in current_by_code.get(code, {}).items():
                            isnaps.setdefault(aid, {})[code] = val
                if need_last_close:
                    for aid, val in closes_by_date.get(d, {}).items():
                        isnaps.setdefault(aid, {})["last_close"] = val

                sv_scores = _evaluate_asset_signal_scores(
                    signals=prep["signals"], asset_signals=prep["asset_signals"],
                    group_signals=prep["group_signals"],
                    params_by_id=prep["params_by_id"],
                    refs_by_key=prep["refs_by_key"], isnaps=isnaps,
                    asset_groups=asset_groups, gscores=gscores)
                sv_rows.extend(
                    {"signal_id": k[0], "asset_id": k[1], "date": d, "score": v}
                    for k, v in sv_scores.items())

                gsv_scores = _evaluate_group_signal_scores(
                    group_signals=prep["group_signals"],
                    params_by_id=prep["params_by_id"],
                    gscores=gscores.values())
                gsv_rows.extend(
                    {"signal_id": k[0], "group_type": k[1], "group_id": k[2],
                     "date": d, "score": v}
                    for k, v in gsv_scores.items())

                # Estrategias: mismos insumos que el camino por-fecha, pero
                # desde memoria (señales recién calculadas + as-of del barrido)
                for ctx in strat_ctx:
                    aids = {aid for (sig_id, aid) in sv_scores
                            if sig_id in ctx["signal_ids"]}
                    groups_sub = {aid: asset_groups[aid] for aid in aids
                                  if aid in asset_groups}
                    operand_values: dict[tuple, dict] = {}
                    for t, key, res in ctx["operands"]:
                        if t == "indicator" and res == "current":
                            operand_values[(t, key, res)] = current_by_code.get(key, {})
                        elif t == "indicator":
                            operand_values[(t, key, res)] = snap.get(key, {})
                        elif t == "signal":
                            op_id = sig_id_by_key.get(key)
                            operand_values[(t, key, res)] = {
                                aid: sc for (sig_id, aid), sc in sv_scores.items()
                                if sig_id == op_id
                            } if op_id is not None else {}
                    scored = rank_strategy_assets(
                        components=ctx["components"], asset_groups=groups_sub,
                        signal_scores=sv_scores, group_scores=gsv_scores,
                        filter_tree=ctx["tree"], operand_values=operand_values)
                    sr_rows.extend(
                        {"strategy_id": ctx["id"], "asset_id": aid, "date": d,
                         "score": score, "rank": rank}
                        for rank, (aid, score) in enumerate(scored, start=1))

                if d not in logged:
                    marker_rows.append(
                        {"scope_kind": eval_kind, "ref_id": eval_ref, "date": d})

            # ── Flush del chunk: DELETE de lo procesado + INSERT masivo ────
            if signal_ids_all:
                s.execute(sa.delete(SignalValue.__table__).where(
                    SignalValue.date.in_(chunk),
                    SignalValue.signal_id.in_(signal_ids_all)))
            if group_sig_ids:
                s.execute(sa.delete(GroupSignalValue.__table__).where(
                    GroupSignalValue.date.in_(chunk),
                    GroupSignalValue.signal_id.in_(group_sig_ids)))
            s.execute(sa.delete(GroupScore.__table__).where(
                GroupScore.date.in_(chunk)))
            if strat_ids:
                s.execute(sa.delete(StrategyResult.__table__).where(
                    StrategyResult.date.in_(chunk),
                    StrategyResult.strategy_id.in_(strat_ids)))

            if gs_rows:
                s.execute(sa.insert(GroupScore.__table__), gs_rows)
            if sv_rows:
                s.execute(sa.insert(SignalValue.__table__), sv_rows)
            if gsv_rows:
                s.execute(sa.insert(GroupSignalValue.__table__), gsv_rows)
            if sr_rows:
                s.execute(sa.insert(StrategyResult.__table__), sr_rows)
            if marker_rows:
                s.execute(sa.insert(SignalEvalLog.__table__), marker_rows)
                logged.update(m["date"] for m in marker_rows)
            s.commit()

            ok += len(chunk)
            logger.info(
                "signal_backfill_range: chunk %s..%s (%d fechas): "
                "%d signal_value, %d group_signal_value, %d group_scores, "
                "%d strategy_result",
                chunk[0], chunk[-1], len(chunk),
                len(sv_rows), len(gsv_rows), len(gs_rows), len(sr_rows))

        except Exception as exc:
            s.rollback()
            logger.exception(
                "signal_backfill_range: chunk %s..%s falló", chunk[0], chunk[-1])
            errors.append({"date": f"{chunk[0]}..{chunk[-1]}",
                           "error": f"chunk {chunk[0]}..{chunk[-1]}: {exc}"})

    return {"total": total, "success": ok, "errors": errors}
