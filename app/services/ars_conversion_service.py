"""
Servicio de conversión automática ARS → otra moneda mediante sintéticos ratio.

Por cada divisor configurado (CCL, MEP, Blue...) y cada activo en moneda ARS
(no sintético) el sistema mantiene un activo sintético tipo ratio:

    TICKER_DIVISOR = TICKER_ARS / DIVISOR

cuyo precio representa el activo valorizado en la moneda del divisor.
"""
import logging

from app.database import get_session
from app.models import Asset, SyntheticComponent, SyntheticFormula
from app.models.ars_conversion import ARSConversionDivisor
from app.models.currency import Currency
from app.models.price_source import PriceSource

logger = logging.getLogger(__name__)


# ── helpers internos ──────────────────────────────────────────────────────────

def _ars_currency_id() -> int | None:
    s = get_session()
    cur = s.query(Currency).filter(Currency.iso_code == "ARS").first()
    if cur:
        return cur.id
    cur = s.query(Currency).filter(Currency.name.ilike("%ARS%")).first()
    return cur.id if cur else None


def _calculado_source_id() -> int | None:
    s = get_session()
    src = s.query(PriceSource).filter(PriceSource.name == "Calculado").first()
    return src.id if src else None


def _syn_ticker(base_ticker: str, div_ticker: str) -> str:
    return f"{base_ticker}_{div_ticker}"


def _syn_name(base_name: str, div_ticker: str) -> str:
    return f"{base_name or '?'} (/{div_ticker})"


# ── consultas ─────────────────────────────────────────────────────────────────

def get_divisors() -> list[ARSConversionDivisor]:
    s = get_session()
    return (
        s.query(ARSConversionDivisor)
         .join(ARSConversionDivisor.divisor_asset)
         .order_by(Asset.ticker)
         .all()
    )


def get_ars_base_assets() -> list[Asset]:
    """Activos con moneda ARS que no son sintéticos (fuente ≠ Calculado)."""
    s      = get_session()
    ars_id = _ars_currency_id()
    cal_id = _calculado_source_id()
    if not ars_id:
        return []
    q = s.query(Asset).filter(Asset.currency_id == ars_id)
    if cal_id:
        q = q.filter(Asset.price_source_id != cal_id)
    return q.order_by(Asset.ticker).all()


def get_stats() -> dict:
    divisors   = get_divisors()
    ars_assets = get_ars_base_assets()
    pairs = [
        (b, d) for b in ars_assets for d in divisors
        if b.id != d.divisor_asset_id
    ]
    expected_tickers = {_syn_ticker(b.ticker, d.divisor_asset.ticker) for b, d in pairs}

    existing = 0
    if expected_tickers:
        s = get_session()
        existing = s.query(Asset).filter(Asset.ticker.in_(expected_tickers)).count()

    return {
        "n_divisors":  len(divisors),
        "n_ars":       len(ars_assets),
        "n_expected":  len(pairs),
        "n_existing":  existing,
        "n_missing":   len(pairs) - existing,
    }


# ── CRUD divisores ────────────────────────────────────────────────────────────

def add_divisor(divisor_asset_id: int) -> ARSConversionDivisor:
    s = get_session()
    existing = s.query(ARSConversionDivisor).filter(
        ARSConversionDivisor.divisor_asset_id == divisor_asset_id
    ).first()
    if existing:
        return existing
    d = ARSConversionDivisor(divisor_asset_id=divisor_asset_id)
    s.add(d)
    s.commit()
    s.refresh(d)
    return d


def remove_divisor(divisor_id: int) -> None:
    s = get_session()
    d = s.query(ARSConversionDivisor).filter(ARSConversionDivisor.id == divisor_id).first()
    if d:
        s.delete(d)
        s.commit()


# ── creación de sintéticos ────────────────────────────────────────────────────

def _ensure_synthetic(base: Asset, div_asset: Asset, calc_src_id: int) -> tuple[Asset, bool]:
    """
    Garantiza que exista el activo sintético y su fórmula ratio.
    Retorna (synthetic_asset, fue_creado).
    """
    s      = get_session()
    ticker = _syn_ticker(base.ticker, div_asset.ticker)

    existing = s.query(Asset).filter(Asset.ticker == ticker).first()
    if existing:
        return existing, False

    syn = Asset(
        ticker          = ticker,
        name            = _syn_name(base.name or base.ticker, div_asset.ticker),
        price_source_id = calc_src_id,
        country_id      = base.country_id,
        market_id       = base.market_id,
        instrument_type_id = base.instrument_type_id,
        currency_id     = None,
        sector_id       = base.sector_id,
        industry_id     = base.industry_id,
        benchmark_id    = None,
    )
    s.add(syn)
    s.flush()

    formula = SyntheticFormula(asset_id=syn.id, formula_type="ratio")
    s.add(formula)
    s.flush()

    s.add(SyntheticComponent(formula_id=formula.id, asset_id=base.id,
                             role="numerator",   weight=1.0))
    s.add(SyntheticComponent(formula_id=formula.id, asset_id=div_asset.id,
                             role="denominator", weight=1.0))
    s.commit()

    logger.info("Sintético ARS creado: %s = %s / %s", ticker, base.ticker, div_asset.ticker)
    return s.query(Asset).filter(Asset.ticker == ticker).first(), True


def count_ars_synthetics_for_divisor(divisor_asset_id: int) -> int:
    """Count synthetic assets where divisor_asset_id is the denominator component."""
    from app.models import SyntheticFormula, SyntheticComponent
    s = get_session()
    formula_ids = [
        row[0] for row in (
            s.query(SyntheticComponent.formula_id)
             .filter(SyntheticComponent.asset_id == divisor_asset_id,
                     SyntheticComponent.role == "denominator")
             .all()
        )
    ]
    if not formula_ids:
        return 0
    return (s.query(SyntheticFormula)
              .filter(SyntheticFormula.id.in_(formula_ids),
                      SyntheticFormula.formula_type == "ratio")
              .count())


def get_ars_currency_id() -> int | None:
    return _ars_currency_id()


def sync_for_asset(asset_id: int) -> dict:
    """Create ARS synthetics for one specific base asset against all configured divisors."""
    from app.services.synthetic_service import compute_synthetic_prices

    s     = get_session()
    base  = s.query(Asset).filter(Asset.id == asset_id).first()
    if not base:
        return {"created": 0, "already_existed": 0, "errors": []}

    ars_id = _ars_currency_id()
    cal_id = _calculado_source_id()
    if not ars_id or base.currency_id != ars_id or base.price_source_id == cal_id:
        return {"created": 0, "already_existed": 0, "errors": []}

    divisors = get_divisors()
    if not divisors or not cal_id:
        return {"created": 0, "already_existed": 0, "errors": []}

    created = 0
    already_existed = 0
    errors = []

    for div in divisors:
        if base.id == div.divisor_asset_id:
            continue
        try:
            syn, was_created = _ensure_synthetic(base, div.divisor_asset, cal_id)
            if was_created:
                created += 1
                try:
                    compute_synthetic_prices(syn.id, full=True)
                except Exception as exc:
                    logger.warning("Error calculando precios %s: %s", syn.ticker, exc)
                    errors.append({"ticker": syn.ticker, "error": str(exc)})
            else:
                already_existed += 1
        except Exception as exc:
            ticker = _syn_ticker(base.ticker, div.divisor_asset.ticker)
            errors.append({"ticker": ticker, "error": str(exc)})

    return {"created": created, "already_existed": already_existed, "errors": errors}


def delete_ars_synthetics_for_asset(asset_id: int) -> int:
    """
    Delete ARS conversion synthetics where asset_id is a component (base or divisor).
    Must be called BEFORE deleting the asset itself (FK RESTRICT).
    Returns count of deleted synthetic assets.
    """
    from app.models import SyntheticFormula, SyntheticComponent

    s           = get_session()
    divisor_ids = {d.divisor_asset_id for d in get_divisors()}
    ars_id      = _ars_currency_id()

    comp_rows = (s.query(SyntheticComponent)
                  .filter(SyntheticComponent.asset_id == asset_id)
                  .all())

    to_delete: set[int] = set()
    for comp in comp_rows:
        formula = (s.query(SyntheticFormula)
                    .filter(SyntheticFormula.id == comp.formula_id,
                            SyntheticFormula.formula_type == "ratio")
                    .first())
        if not formula:
            continue

        all_comps = (s.query(SyntheticComponent)
                      .filter(SyntheticComponent.formula_id == formula.id)
                      .all())
        num_ids = {c.asset_id for c in all_comps if c.role == "numerator"}
        den_ids = {c.asset_id for c in all_comps if c.role == "denominator"}

        # ARS synthetic ↔ denominator is a known divisor OR numerator has ARS currency
        is_ars = bool(den_ids & divisor_ids)
        if not is_ars and ars_id:
            for nid in num_ids:
                a = s.query(Asset).filter(Asset.id == nid).first()
                if a and a.currency_id == ars_id:
                    is_ars = True
                    break

        if is_ars:
            to_delete.add(formula.asset_id)

    count = 0
    for aid in to_delete:
        syn = s.query(Asset).filter(Asset.id == aid).first()
        if syn:
            s.delete(syn)
            count += 1

    if count:
        s.commit()
    return count


def sync_all(progress_cb=None) -> dict:
    """
    Para cada divisor activo × cada activo ARS: garantiza que existe el
    sintético y calcula sus precios si fue recién creado.

    Retorna {created, already_existed, computed, errors}.
    """
    from app.services.synthetic_service import compute_synthetic_prices

    divisors   = get_divisors()
    ars_assets = get_ars_base_assets()
    cal_id     = _calculado_source_id()

    if not divisors or not ars_assets or not cal_id:
        return {"created": 0, "already_existed": 0, "computed": 0, "errors": []}

    pairs = [
        (b, d) for b in ars_assets for d in divisors
        if b.id != d.divisor_asset_id
    ]
    total          = len(pairs)
    created        = 0
    already_existed = 0
    computed       = 0
    errors         = []

    for i, (base, div) in enumerate(pairs):
        if progress_cb:
            progress_cb(i + 1, total)
        try:
            syn, was_created = _ensure_synthetic(base, div.divisor_asset, cal_id)
            if was_created:
                created += 1
                try:
                    compute_synthetic_prices(syn.id, full=True)
                    computed += 1
                except Exception as exc:
                    logger.warning("Error calculando precios %s: %s", syn.ticker, exc)
                    errors.append({"ticker": syn.ticker, "error": str(exc)})
            else:
                already_existed += 1
        except Exception as exc:
            ticker = _syn_ticker(base.ticker, div.divisor_asset.ticker)
            logger.warning("Error creando sintético %s: %s", ticker, exc)
            errors.append({"ticker": ticker, "error": str(exc)})

    return {
        "created":         created,
        "already_existed": already_existed,
        "computed":        computed,
        "errors":          errors,
    }
