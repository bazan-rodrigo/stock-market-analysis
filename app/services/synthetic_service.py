"""
Servicio de activos sintéticos.

Tipos de fórmula soportados
────────────────────────────
ratio        precio = Σ(w_i·P_i  |  role=numerator) / Σ(w_i·P_i  |  role=denominator)
weighted_avg precio = Σ(w_i·P_i) / Σ(w_i)
weighted_sum precio = Σ(w_i·P_i)
index        precio = base_value · Σ(w_i·P_i/P_base_i) / Σ(w_i)
             donde P_base_i es el precio del activo i en base_date
"""
import logging
from datetime import date as _date

from sqlalchemy import func

from app.database import get_session
from app.models import Asset, Price, SyntheticComponent, SyntheticFormula
from app.services.screener_service import compute_and_save_snapshot

logger = logging.getLogger(__name__)


# ── Consultas ─────────────────────────────────────────────────────────────────

def get_all_formulas() -> list[SyntheticFormula]:
    s = get_session()
    return s.query(SyntheticFormula).all()


def get_formula_by_asset(asset_id: int) -> SyntheticFormula | None:
    s = get_session()
    return s.query(SyntheticFormula).filter(SyntheticFormula.asset_id == asset_id).first()


def is_synthetic(asset_id: int) -> bool:
    return get_formula_by_asset(asset_id) is not None


def get_assets_options_for_synthetic() -> list[dict]:
    """Activos activos con fuente 'Calculado' (destino de una fórmula)."""
    from app.models import PriceSource
    s = get_session()
    src = s.query(PriceSource).filter(PriceSource.name == "Calculado").first()
    if src is None:
        return []
    assets = (s.query(Asset)
               .filter(Asset.price_source_id == src.id)
               .order_by(Asset.ticker).all())
    return [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets]


def get_all_assets_options() -> list[dict]:
    s = get_session()
    assets = s.query(Asset).order_by(Asset.ticker).all()
    return [{"label": f"{a.ticker} — {a.name}", "value": a.id} for a in assets]


# ── CRUD ──────────────────────────────────────────────────────────────────────

def save_formula(
    asset_id: int,
    formula_type: str,
    components: list[dict],     # [{asset_id, role, weight}]
    base_value: float | None = None,
    base_date: _date | None = None,
    formula_id: int | None = None,
) -> SyntheticFormula:
    s = get_session()
    if formula_id:
        f = s.query(SyntheticFormula).filter(SyntheticFormula.id == formula_id).first()
        if f is None:
            raise ValueError(f"Fórmula id={formula_id} no encontrada")
        s.query(SyntheticComponent).filter(SyntheticComponent.formula_id == formula_id).delete()
    else:
        existing = s.query(SyntheticFormula).filter(SyntheticFormula.asset_id == asset_id).first()
        if existing:
            f = existing
            s.query(SyntheticComponent).filter(SyntheticComponent.formula_id == f.id).delete()
        else:
            f = SyntheticFormula(asset_id=asset_id)
            s.add(f)

    f.formula_type = formula_type
    f.base_value   = base_value
    f.base_date    = base_date
    s.flush()  # flush después de asignar atributos para que el INSERT no tenga NULLs

    for comp in components:
        s.add(SyntheticComponent(
            formula_id=f.id,
            asset_id=int(comp["asset_id"]),
            role=comp["role"],
            weight=float(comp.get("weight") or 1.0),
        ))

    s.commit()
    s.refresh(f)
    return f


def delete_formula(formula_id: int) -> None:
    s = get_session()
    f = s.query(SyntheticFormula).filter(SyntheticFormula.id == formula_id).first()
    if f:
        s.delete(f)
        s.commit()


# ── Cálculo de precios ────────────────────────────────────────────────────────

def _load_price_map(asset_id: int, start_date=None) -> dict:
    """Retorna {date: Price} para el activo dado."""
    s = get_session()
    q = s.query(Price).filter(Price.asset_id == asset_id)
    if start_date:
        q = q.filter(Price.date >= start_date)
    return {p.date: p for p in q.all()}


def _common_dates(maps: list[dict]) -> list:
    if not maps:
        return []
    common = set(maps[0].keys())
    for m in maps[1:]:
        common &= set(m.keys())
    return sorted(common)


def _safe_open(price, fallback_close):
    return price.open if price.open else fallback_close


def compute_synthetic_prices(asset_id: int, full: bool = False) -> int:
    s = get_session()
    formula = get_formula_by_asset(asset_id)
    if formula is None:
        raise ValueError(f"Sin fórmula para activo id={asset_id}")

    if full:
        s.query(Price).filter(Price.asset_id == asset_id).delete()
        s.commit()
        start_date = None
    else:
        last_date = (s.query(func.max(Price.date))
                      .filter(Price.asset_id == asset_id).scalar())
        if last_date:
            s.query(Price).filter(Price.asset_id == asset_id,
                                  Price.date >= last_date).delete()
            s.commit()
            start_date = last_date
        else:
            start_date = None

    comps = formula.components
    all_asset_ids = list({c.asset_id for c in comps})
    price_maps = {aid: _load_price_map(aid, start_date) for aid in all_asset_ids}

    results = _compute_by_type(formula, comps, price_maps)

    count = 0
    for d, vals in sorted(results.items()):
        s.add(Price(
            asset_id=asset_id,
            date=d,
            open=round(vals["open"],  8),
            high=round(vals["high"],  8),
            low=round(vals["low"],   8),
            close=round(vals["close"], 8),
            volume=None,
        ))
        count += 1

    s.commit()
    logger.info("Sintético id=%d: %d precios (%s, full=%s)", asset_id, count,
                formula.formula_type, full)

    try:
        compute_and_save_snapshot(asset_id)
    except Exception as exc:
        logger.warning("Error snapshot sintético id=%d: %s", asset_id, exc)

    return count


def _compute_by_type(formula, comps, price_maps) -> dict:
    ft = formula.formula_type

    if ft == "ratio":
        nums = [(c.weight, c.asset_id) for c in comps if c.role == "numerator"]
        dens = [(c.weight, c.asset_id) for c in comps if c.role == "denominator"]
        all_ids = [aid for _, aid in nums + dens]
        dates = _common_dates([price_maps[aid] for aid in all_ids])
        out = {}
        for d in dates:
            num_c = sum(w * price_maps[aid][d].close for w, aid in nums)
            den_c = sum(w * price_maps[aid][d].close for w, aid in dens)
            if not den_c:
                continue
            close = num_c / den_c
            num_o = sum(w * _safe_open(price_maps[aid][d], price_maps[aid][d].close) for w, aid in nums)
            den_o = sum(w * _safe_open(price_maps[aid][d], price_maps[aid][d].close) for w, aid in dens)
            open_ = num_o / den_o if den_o else close
            out[d] = {"open": open_, "close": close,
                      "high": max(open_, close), "low": min(open_, close)}
        return out

    if ft in ("weighted_avg", "weighted_sum"):
        comps_c = [(c.weight, c.asset_id) for c in comps if c.role == "component"]
        all_ids = [aid for _, aid in comps_c]
        dates = _common_dates([price_maps[aid] for aid in all_ids])
        total_w = sum(w for w, _ in comps_c)
        divisor = total_w if (ft == "weighted_avg" and total_w) else 1.0
        out = {}
        for d in dates:
            close = sum(w * price_maps[aid][d].close for w, aid in comps_c) / divisor
            open_ = sum(w * _safe_open(price_maps[aid][d], price_maps[aid][d].close)
                        for w, aid in comps_c) / divisor
            out[d] = {"open": open_, "close": close,
                      "high": max(open_, close), "low": min(open_, close)}
        return out

    if ft == "index":
        comps_c = [(c.weight, c.asset_id) for c in comps if c.role == "component"]
        all_ids = [aid for _, aid in comps_c]
        base_val = formula.base_value or 100.0
        base_dt  = formula.base_date

        # Precio base de cada componente en base_date
        base_prices = {}
        for _, aid in comps_c:
            pm = price_maps[aid]
            if base_dt and base_dt in pm:
                base_prices[aid] = pm[base_dt].close
            elif pm:
                # Fecha más cercana anterior a base_date
                candidates = [d for d in pm if (not base_dt or d <= base_dt)]
                if candidates:
                    base_prices[aid] = pm[max(candidates)].close

        dates = _common_dates([price_maps[aid] for aid in all_ids])
        total_w = sum(w for w, _ in comps_c) or 1.0
        out = {}
        for d in dates:
            close_sum = 0.0
            open_sum  = 0.0
            for w, aid in comps_c:
                bp = base_prices.get(aid)
                if not bp:
                    continue
                close_sum += w * price_maps[aid][d].close / bp
                open_sum  += w * _safe_open(price_maps[aid][d], price_maps[aid][d].close) / bp
            close = base_val * close_sum / total_w
            open_ = base_val * open_sum  / total_w
            out[d] = {"open": open_, "close": close,
                      "high": max(open_, close), "low": min(open_, close)}
        return out

    return {}


def compute_all_synthetic(progress_cb=None) -> dict:
    formulas = get_all_formulas()
    errors   = []
    for i, f in enumerate(formulas):
        if progress_cb:
            progress_cb(i + 1, len(formulas))
        try:
            compute_synthetic_prices(f.asset_id, full=False)
        except Exception as exc:
            ticker = f.asset.ticker if f.asset else str(f.asset_id)
            logger.warning("Error sintético %s: %s", ticker, exc)
            errors.append({"ticker": ticker, "error": str(exc)})
    return {"total": len(formulas), "errors": errors}


def formula_preview_str(formula: SyntheticFormula) -> str:
    ticker = formula.asset.ticker if formula.asset else "?"
    ft = formula.formula_type
    comps = formula.components

    def label(c):
        return c.asset.ticker if c.asset else f"id={c.asset_id}"

    if ft == "ratio":
        nums = [f"{c.weight}×{label(c)}" if c.weight != 1 else label(c)
                for c in comps if c.role == "numerator"]
        dens = [f"{c.weight}×{label(c)}" if c.weight != 1 else label(c)
                for c in comps if c.role == "denominator"]
        return f"{ticker} = ({' + '.join(nums)}) / ({' + '.join(dens)})"

    if ft == "weighted_avg":
        parts = [f"{c.weight}×{label(c)}" for c in comps if c.role == "component"]
        total_w = sum(c.weight for c in comps if c.role == "component")
        return f"{ticker} = ({' + '.join(parts)}) / {total_w:.4g}"

    if ft == "weighted_sum":
        parts = [f"{c.weight}×{label(c)}" for c in comps if c.role == "component"]
        return f"{ticker} = {' + '.join(parts)}"

    if ft == "index":
        parts = [f"{c.weight}×{label(c)}/P₀" for c in comps if c.role == "component"]
        total_w = sum(c.weight for c in comps if c.role == "component")
        bv = formula.base_value or 100
        bd = str(formula.base_date) if formula.base_date else "?"
        return f"{ticker} = {bv} × ({' + '.join(parts)}) / {total_w:.4g}   [base: {bd}]"

    return ticker
