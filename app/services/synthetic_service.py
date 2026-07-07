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
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date as _date

import numpy as np
import pandas as pd
from sqlalchemy import func

from app.database import get_session, Session as _ScopedSession
from app.models import Asset, Price, SyntheticComponent, SyntheticFormula
from app.services.technical_service import compute_current_indicators, _save_indicator_log

logger = logging.getLogger(__name__)

# Sintéticos por nivel de dependencia procesados en paralelo (ver _topological_levels)
_SYN_WORKERS = 4


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

def _load_price_frame(asset_id: int, start_date=None) -> pd.DataFrame:
    """DataFrame indexado por fecha con columnas 'close' y 'eff_open' (open si es
    válido —no nulo ni cero—, si no el close de esa misma fecha). Trae solo las
    columnas necesarias en vez de objetos ORM completos: para historiales largos
    x muchos componentes evita instanciar miles de objetos Price por nada."""
    s = get_session()
    q = s.query(Price.date, Price.open, Price.close).filter(Price.asset_id == asset_id)
    if start_date:
        q = q.filter(Price.date >= start_date)
    rows = q.all()
    if not rows:
        return pd.DataFrame(columns=["close", "eff_open"])
    df = pd.DataFrame(rows, columns=["date", "open", "close"]).set_index("date")
    df["eff_open"] = df["open"].where(df["open"].notna() & (df["open"] != 0), df["close"])
    return df[["close", "eff_open"]]


def _common_index(asset_ids: list[int], price_frames: dict) -> pd.Index:
    ids = list(dict.fromkeys(asset_ids))
    if not ids:
        return pd.Index([])
    common = price_frames[ids[0]].index
    for aid in ids[1:]:
        common = common.intersection(price_frames[aid].index)
    return common.sort_values()


def _weighted_sums(items: list[tuple[float, int]], price_frames: dict,
                    common: pd.Index) -> tuple[np.ndarray, np.ndarray]:
    """Σ(w·close) y Σ(w·eff_open) de `items` en las fechas de `common`."""
    close_sum = np.zeros(len(common))
    open_sum  = np.zeros(len(common))
    for w, aid in items:
        f = price_frames[aid].loc[common]
        close_sum += w * f["close"].to_numpy()
        open_sum  += w * f["eff_open"].to_numpy()
    return close_sum, open_sum


def _anchor_price(asset_id: int, base_date, session) -> float | None:
    """Precio de cierre de un componente en base_date (o la fecha válida anterior
    más cercana; la última disponible si base_date es None). Query liviana e
    independiente de la ventana tail-mode del delta: un sintético 'index'
    calculado incrementalmente solo carga precios desde last_date en adelante,
    y su base_date suele ser muy anterior a esa ventana — sin esto, el precio
    base no se encontraba y el componente se excluía en silencio."""
    q = session.query(Price.close).filter(Price.asset_id == asset_id, Price.close.isnot(None))
    if base_date:
        q = q.filter(Price.date <= base_date)
    row = q.order_by(Price.date.desc()).first()
    return float(row[0]) if row and row[0] is not None else None


def _ohlc_dict(common: pd.Index, open_: np.ndarray, close: np.ndarray,
               mask: np.ndarray | None = None) -> dict:
    high = np.maximum(open_, close)
    low  = np.minimum(open_, close)
    idx  = range(len(common)) if mask is None else np.flatnonzero(mask)
    return {
        common[i]: {"open": float(open_[i]), "close": float(close[i]),
                    "high": float(high[i]), "low": float(low[i])}
        for i in idx
    }


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
    price_frames = {aid: _load_price_frame(aid, start_date) for aid in all_asset_ids}

    base_prices = None
    if formula.formula_type == "index":
        # Resuelto aparte de price_frames: en modo incremental (tail-mode)
        # price_frames no cubre fechas anteriores a start_date, pero base_date sí
        # puede serlo. Ver _anchor_price.
        base_prices = {}
        for aid in all_asset_ids:
            bp = _anchor_price(aid, formula.base_date, s)
            if bp is not None:
                base_prices[aid] = bp

    results = _compute_by_type(formula, comps, price_frames, base_prices=base_prices)

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
        compute_current_indicators(asset_id, quick=not full)
        if full or start_date is None:
            # Historia de precios nueva o reconstruida → rehacer también la
            # historia de indicadores (el quick solo escribe el último día)
            backfill_asset_history(asset_id)
        _save_indicator_log(asset_id, success=True, error=None, session=s)
    except Exception as exc:
        logger.warning("Error indicadores sintético id=%d: %s", asset_id, exc)
        _save_indicator_log(asset_id, success=False, error=str(exc), session=s)

    return count


def _compute_by_type(formula, comps, price_frames: dict,
                      base_prices: dict | None = None) -> dict:
    """Vectorizado con pandas/numpy: sin loops por fecha en Python puro.
    Semántica idéntica a la versión escalar anterior (paridad cubierta por
    tests/test_synthetic_service.py).

    base_prices (solo para formula_type='index'): precios base ya resueltos
    por el llamador vía _anchor_price, que no dependen de la ventana tail-mode
    de price_frames. Si no se provee, se resuelve a partir de price_frames
    (comportamiento anterior, usado en los tests unitarios sin DB)."""
    ft = formula.formula_type

    if ft == "ratio":
        nums = [(c.weight, c.asset_id) for c in comps if c.role == "numerator"]
        dens = [(c.weight, c.asset_id) for c in comps if c.role == "denominator"]
        all_ids = [aid for _, aid in nums + dens]
        common = _common_index(all_ids, price_frames)
        if common.empty:
            return {}
        num_c, num_o = _weighted_sums(nums, price_frames, common)
        den_c, den_o = _weighted_sums(dens, price_frames, common)
        mask = den_c != 0
        with np.errstate(divide="ignore", invalid="ignore"):
            close = np.divide(num_c, den_c)
            open_raw = np.divide(num_o, den_o)
        open_ = np.where(den_o != 0, open_raw, close)
        return _ohlc_dict(common, open_, close, mask)

    if ft in ("weighted_avg", "weighted_sum"):
        comps_c = [(c.weight, c.asset_id) for c in comps if c.role == "component"]
        all_ids = [aid for _, aid in comps_c]
        common = _common_index(all_ids, price_frames)
        if common.empty:
            return {}
        total_w = sum(w for w, _ in comps_c)
        divisor = total_w if (ft == "weighted_avg" and total_w) else 1.0
        close_sum, open_sum = _weighted_sums(comps_c, price_frames, common)
        close = close_sum / divisor
        open_ = open_sum  / divisor
        return _ohlc_dict(common, open_, close)

    if ft == "index":
        comps_c = [(c.weight, c.asset_id) for c in comps if c.role == "component"]
        all_ids = [aid for _, aid in comps_c]
        base_val = formula.base_value or 100.0
        base_dt  = formula.base_date

        if base_prices is None:
            # Fallback: resolver el precio base a partir de price_frames (solo
            # correcto si price_frames cubre hasta base_date, p. ej. en tests
            # o en un cálculo full sin ventana tail).
            base_prices = {}
            for _, aid in comps_c:
                f = price_frames[aid]
                if base_dt and base_dt in f.index:
                    base_prices[aid] = float(f.loc[base_dt, "close"])
                elif not f.empty:
                    # Fecha más cercana anterior a base_date
                    candidates = f.index[f.index <= base_dt] if base_dt else f.index
                    if len(candidates):
                        base_prices[aid] = float(f.loc[candidates.max(), "close"])

        common = _common_index(all_ids, price_frames)
        if common.empty:
            return {}
        total_w = sum(w for w, _ in comps_c) or 1.0
        close_sum = np.zeros(len(common))
        open_sum  = np.zeros(len(common))
        for w, aid in comps_c:
            bp = base_prices.get(aid)
            if not bp:
                continue
            f = price_frames[aid].loc[common]
            close_sum += w * f["close"].to_numpy()    / bp
            open_sum  += w * f["eff_open"].to_numpy() / bp
        close = base_val * close_sum / total_w
        open_ = base_val * open_sum  / total_w
        return _ohlc_dict(common, open_, close)

    return {}


def _topological_levels(formulas: list[SyntheticFormula]) -> list[list[SyntheticFormula]]:
    """Agrupa las fórmulas en niveles de dependencia: un sintético que usa a otro
    sintético como componente queda en un nivel posterior al de su dependencia.
    Dentro de un nivel el orden no importa (se puede paralelizar); entre niveles
    sí, porque el nivel siguiente necesita los precios ya recalculados del
    anterior. Nada en el modelo impide encadenar sintéticos, así que sin esto
    un sintético-de-sintético podía leer el precio de la corrida anterior."""
    syn_ids  = {f.asset_id for f in formulas}
    by_asset = {f.asset_id: f for f in formulas}
    remaining = {
        f.asset_id: {c.asset_id for c in f.components if c.asset_id in syn_ids}
        for f in formulas
    }
    levels: list[list[SyntheticFormula]] = []
    done: set[int] = set()
    while remaining:
        ready = [aid for aid, deps in remaining.items() if deps <= done]
        if not ready:
            # Dependencia circular: no hay forma de ordenarlos sin colgar el
            # proceso. Se procesan todos juntos en un último nivel — el
            # resultado puede quedar un ciclo desactualizado, pero no bloquea.
            ready = list(remaining.keys())
            logger.warning("Ciclo de dependencias entre sintéticos: %s",
                            [by_asset[aid].asset.ticker for aid in ready])
        levels.append([by_asset[aid] for aid in ready])
        done.update(ready)
        for aid in ready:
            remaining.pop(aid)
    return levels


def compute_all_synthetic(progress_cb=None, *, full: bool = False) -> dict:
    formulas = get_all_formulas()
    total    = len(formulas)
    errors: list[dict] = []
    done     = 0
    lock     = threading.Lock()
    if progress_cb:
        progress_cb(0, total)

    def _worker(f: SyntheticFormula):
        try:
            compute_synthetic_prices(f.asset_id, full=full)
            return None
        except Exception as exc:
            ticker = f.asset.ticker if f.asset else str(f.asset_id)
            logger.warning("Error sintético %s: %s", ticker, exc)
            return {"ticker": ticker, "error": str(exc)}
        finally:
            _ScopedSession.remove()

    for level in _topological_levels(formulas):
        with ThreadPoolExecutor(max_workers=min(len(level), _SYN_WORKERS)) as pool:
            futures = [pool.submit(_worker, f) for f in level]
            for future in as_completed(futures):
                err = future.result()
                with lock:
                    done += 1
                    if progress_cb:
                        progress_cb(done, total)
                    if err:
                        errors.append(err)
    return {"total": total, "errors": errors}


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


# ── Exportación / Importación de fórmulas ────────────────────────────────────

def export_formulas_excel() -> bytes:
    """Exporta todas las fórmulas sintéticas como Excel (una fila por componente)."""
    import openpyxl
    from io import BytesIO

    formulas = get_all_formulas()
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Fórmulas"
    ws.append([
        "synthetic_ticker", "formula_type", "base_value", "base_date",
        "component_ticker", "role", "weight",
    ])
    for f in formulas:
        syn_ticker = f.asset.ticker if f.asset else ""
        for c in f.components:
            comp_ticker = c.asset.ticker if c.asset else ""
            ws.append([
                syn_ticker,
                f.formula_type,
                f.base_value if f.base_value is not None else "",
                str(f.base_date) if f.base_date else "",
                comp_ticker,
                c.role,
                c.weight,
            ])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


def import_formulas_excel(file_bytes: bytes) -> list[dict]:
    """
    Importa fórmulas desde Excel.
    Garantías:
    - El activo sintético debe existir con fuente Calculado.
    - Todos los componentes deben existir como activos.
    - Si la fórmula ya existe para el activo, se reemplaza.
    Devuelve lista de resultados por synthetic_ticker.
    """
    import pandas as pd
    from io import BytesIO
    from datetime import date as _date

    try:
        df = pd.read_excel(BytesIO(file_bytes), dtype=str)
    except Exception as exc:
        raise ValueError(f"Error leyendo el archivo: {exc}") from exc

    df.columns = [c.strip().lower() for c in df.columns]
    required = {"synthetic_ticker", "formula_type", "component_ticker", "role", "weight"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Columnas faltantes: {missing}")

    s = get_session()

    # Agrupar por synthetic_ticker
    grouped: dict[str, list] = {}
    for _, row in df.iterrows():
        syn = str(row.get("synthetic_ticker", "")).strip().upper()
        if not syn:
            continue
        grouped.setdefault(syn, []).append(row)

    results = []
    for syn_ticker, rows in grouped.items():
        status, detail = "error", ""
        try:
            # Verificar que el activo sintético existe con fuente Calculado
            syn_asset = s.query(Asset).filter(Asset.ticker == syn_ticker).first()
            if syn_asset is None:
                raise ValueError(f"Activo '{syn_ticker}' no encontrado")
            src = syn_asset.price_source
            if src is None or src.name != "Calculado":
                raise ValueError(
                    f"Activo '{syn_ticker}' no tiene fuente 'Calculado' (tiene '{src.name if src else 'ninguna'}')"
                )

            # Tomar metadatos de la primera fila
            first = rows[0]
            ft = str(first.get("formula_type", "")).strip()
            if ft not in ("ratio", "weighted_avg", "weighted_sum", "index"):
                raise ValueError(f"Tipo de fórmula inválido: '{ft}'")

            bv_raw = str(first.get("base_value", "")).strip()
            base_value = float(bv_raw) if bv_raw and bv_raw.lower() not in ("nan", "") else None

            bd_raw = str(first.get("base_date", "")).strip()
            try:
                base_date = _date.fromisoformat(bd_raw[:10]) if bd_raw and bd_raw.lower() not in ("nan", "") else None
            except ValueError:
                base_date = None

            # Resolver componentes
            components = []
            for row in rows:
                comp_ticker = str(row.get("component_ticker", "")).strip().upper()
                role        = str(row.get("role", "component")).strip()
                weight_raw  = str(row.get("weight", "1")).strip()
                try:
                    weight = float(weight_raw)
                except ValueError:
                    weight = 1.0

                comp_asset = s.query(Asset).filter(Asset.ticker == comp_ticker).first()
                if comp_asset is None:
                    raise ValueError(f"Componente '{comp_ticker}' no encontrado")
                components.append({"asset_id": comp_asset.id, "role": role, "weight": weight})

            save_formula(
                asset_id=syn_asset.id,
                formula_type=ft,
                components=components,
                base_value=base_value,
                base_date=base_date,
            )
            status = "imported"
            detail = f"{len(components)} componente(s) importado(s)"
        except Exception as exc:
            status = "error"
            detail = str(exc)
            logger.warning("Import fórmula %s: %s", syn_ticker, exc)

        results.append({"ticker": syn_ticker, "status": status, "detail": detail})

    return results
