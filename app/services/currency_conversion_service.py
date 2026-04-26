"""
Servicio de conversión de monedas mediante activos sintéticos ratio.

Por cada par (moneda_fuente, divisor) configurado, y cada activo en esa moneda
(no sintético), el sistema mantiene un activo sintético tipo ratio:

    TICKER_SINTÉTICO = TICKER_BASE / TICKER_DIVISOR

cuyo precio representa el activo valorizado en la moneda del divisor.
"""
import logging

from app.database import get_session
from app.models import Asset, SyntheticComponent, SyntheticFormula
from app.models.currency_conversion import CurrencyConversionDivisor
from app.models.price_source import PriceSource

logger = logging.getLogger(__name__)


# ── helpers internos ──────────────────────────────────────────────────────────

def _calculado_source_id() -> int | None:
    s = get_session()
    src = s.query(PriceSource).filter(PriceSource.name == "Calculado").first()
    return src.id if src else None


def _syn_ticker(base_ticker: str, div_ticker: str) -> str:
    return f"{base_ticker}_{div_ticker}"


def _syn_name(base_name: str, div_ticker: str) -> str:
    return f"{base_name or '?'} (/{div_ticker})"


# ── consultas ─────────────────────────────────────────────────────────────────

def get_divisors(currency_id: int | None = None) -> list[CurrencyConversionDivisor]:
    s = get_session()
    q = (s.query(CurrencyConversionDivisor)
          .join(CurrencyConversionDivisor.divisor_asset)
          .order_by(Asset.ticker))
    if currency_id is not None:
        q = q.filter(CurrencyConversionDivisor.currency_id == currency_id)
    return q.all()


def get_base_assets_for_currency(currency_id: int) -> list[Asset]:
    """Activos con la moneda dada que no son sintéticos (fuente ≠ Calculado)."""
    s      = get_session()
    cal_id = _calculado_source_id()
    q = s.query(Asset).filter(Asset.currency_id == currency_id)
    if cal_id:
        q = q.filter(Asset.price_source_id != cal_id)
    return q.order_by(Asset.ticker).all()


def get_stats() -> list[dict]:
    """Retorna una fila de stats por cada moneda configurada."""
    all_divisors = get_divisors()
    if not all_divisors:
        return []

    # Agrupar por moneda
    by_currency: dict = {}
    for d in all_divisors:
        by_currency.setdefault(d.currency, []).append(d)

    s = get_session()
    result = []
    for currency, divisors in by_currency.items():
        base_assets = get_base_assets_for_currency(currency.id)
        pairs = [
            (b, d) for b in base_assets for d in divisors
            if b.id != d.divisor_asset_id
        ]
        expected_tickers = {_syn_ticker(b.ticker, d.divisor_asset.ticker) for b, d in pairs}
        existing = (s.query(Asset).filter(Asset.ticker.in_(expected_tickers)).count()
                    if expected_tickers else 0)
        result.append({
            "currency":   currency,
            "n_divisors": len(divisors),
            "n_base":     len(base_assets),
            "n_expected": len(pairs),
            "n_existing": existing,
            "n_missing":  len(pairs) - existing,
        })
    return result


# ── CRUD divisores ────────────────────────────────────────────────────────────

def add_divisor(currency_id: int, divisor_asset_id: int) -> CurrencyConversionDivisor:
    s = get_session()
    existing = s.query(CurrencyConversionDivisor).filter(
        CurrencyConversionDivisor.currency_id      == currency_id,
        CurrencyConversionDivisor.divisor_asset_id == divisor_asset_id,
    ).first()
    if existing:
        return existing
    d = CurrencyConversionDivisor(currency_id=currency_id, divisor_asset_id=divisor_asset_id)
    s.add(d)
    s.commit()
    s.refresh(d)
    return d


def remove_divisor(divisor_id: int) -> None:
    s = get_session()
    d = s.query(CurrencyConversionDivisor).filter(CurrencyConversionDivisor.id == divisor_id).first()
    if d:
        s.delete(d)
        s.commit()


def count_synthetics_for_divisor(divisor_asset_id: int) -> int:
    """Cuenta sintéticos donde divisor_asset_id es el denominador."""
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


# ── creación de sintéticos ────────────────────────────────────────────────────

def _ensure_synthetic(base: Asset, div_asset: Asset, calc_src_id: int) -> tuple[Asset, bool]:
    s      = get_session()
    ticker = _syn_ticker(base.ticker, div_asset.ticker)

    existing = s.query(Asset).filter(Asset.ticker == ticker).first()
    if existing:
        return existing, False

    syn = Asset(
        ticker             = ticker,
        name               = _syn_name(base.name or base.ticker, div_asset.ticker),
        price_source_id    = calc_src_id,
        country_id         = base.country_id,
        market_id          = base.market_id,
        instrument_type_id = base.instrument_type_id,
        currency_id        = div_asset.currency_id,
        sector_id          = base.sector_id,
        industry_id        = base.industry_id,
        benchmark_id       = None,
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

    logger.info("Sintético creado: %s = %s / %s", ticker, base.ticker, div_asset.ticker)
    return s.query(Asset).filter(Asset.ticker == ticker).first(), True


def delete_synthetics_for_asset(asset_id: int) -> int:
    """
    Elimina los sintéticos de conversión donde asset_id es componente (base o divisor).
    Debe llamarse ANTES de eliminar el activo (FK RESTRICT en SyntheticComponent).
    Retorna la cantidad de sintéticos eliminados.
    """
    s               = get_session()
    all_divisor_ids = {d.divisor_asset_id for d in get_divisors()}
    configured_curs = {d.currency_id      for d in get_divisors()}

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

        # Es sintético de conversión si el denominador es un divisor conocido
        # o el numerador tiene una moneda configurada
        is_conv = bool(den_ids & all_divisor_ids)
        if not is_conv and configured_curs:
            for nid in num_ids:
                a = s.query(Asset).filter(Asset.id == nid).first()
                if a and a.currency_id in configured_curs:
                    is_conv = True
                    break

        if is_conv:
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


def sync_for_asset(asset_id: int) -> dict:
    """Crea los sintéticos para un activo base contra todos los divisores de su moneda."""
    from app.services.synthetic_service import compute_synthetic_prices

    s    = get_session()
    base = s.query(Asset).filter(Asset.id == asset_id).first()
    if not base or not base.currency_id:
        return {"created": 0, "already_existed": 0, "errors": []}

    cal_id = _calculado_source_id()
    if not cal_id or base.price_source_id == cal_id:
        return {"created": 0, "already_existed": 0, "errors": []}

    divisors = get_divisors(currency_id=base.currency_id)
    if not divisors:
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


def sync_all(progress_cb=None) -> dict:
    """
    Para cada par (moneda, divisor) × cada activo en esa moneda: garantiza que
    existe el sintético y calcula sus precios si fue recién creado.
    """
    from app.services.synthetic_service import compute_synthetic_prices

    all_divisors = get_divisors()
    cal_id       = _calculado_source_id()
    if not all_divisors or not cal_id:
        return {"created": 0, "already_existed": 0, "computed": 0, "errors": []}

    # Agrupar divisores por moneda para evitar consultas repetidas
    by_currency: dict = {}
    for d in all_divisors:
        by_currency.setdefault(d.currency_id, []).append(d)

    pairs = []
    for currency_id, divisors in by_currency.items():
        for base in get_base_assets_for_currency(currency_id):
            for div in divisors:
                if base.id != div.divisor_asset_id:
                    pairs.append((base, div))

    total           = len(pairs)
    created         = 0
    already_existed = 0
    computed        = 0
    errors          = []

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
