"""
Almacenamiento de indicadores por tabla separada.

Cada indicador con keep_history=True tiene su propia tabla ind_{code}
con PK (asset_id, date), sin contención entre indicadores al escribir.

Los indicadores con keep_history=False (best_sma_*, best_ema_*) se
almacenan en current_indicator_values (un solo valor vigente por activo).
"""
import os
import threading

from sqlalchemy import (Column, Date, Float, ForeignKey, Index, Integer,
                        MetaData, PrimaryKeyConstraint, String, Table)

from app.database import Base, engine

_meta      = MetaData()
_meta_lock = threading.Lock()


# ── Tablas anchas por cadencia (ind_daily/ind_weekly/ind_monthly) ─────────────
# Optimización de footprint (docs/notes/design_ind_wide_tables.md): los
# indicadores técnicos con historia se agrupan en 3 tablas anchas por cadencia
# — una fila por (asset_id, date), una columna por indicador — en vez de una
# tabla ind_{code} por indicador. Paga el overhead de fila+índice de InnoDB una
# vez por fecha en lugar de N veces. Lossless: mismas filas, fechas y valores.
#
# El nombre de columna ES el code. return_monthly/quarterly/yearly son cadencia
# DIARIA (rolling calculado cada día) pese al nombre. Los fundamentales (otro
# servicio) y los keep_history=False quedan fuera: camino legacy per-tabla.
_WIDE_DAILY = [
    "trend_daily", "volatility_daily", "atr_percentile_daily", "rsi_daily",
    "dist_sma20", "dist_sma50", "dist_sma200", "dist_optimal_sma_daily",
    "return_daily", "return_monthly", "return_quarterly", "return_yearly",
    "return_52w", "relative_strength_52w",
]
_WIDE_WEEKLY = [
    "trend_weekly", "volatility_weekly", "atr_percentile_weekly",
    "rsi_weekly", "dist_optimal_sma_weekly",
]
_WIDE_MONTHLY = [
    "trend_monthly", "volatility_monthly", "atr_percentile_monthly",
    "rsi_monthly", "dist_optimal_sma_monthly",
]
# Fundamentales, los escribe fundamental_service. DIARIOS (dependen del precio,
# densos) → ind_fundamental_daily. TRIMESTRALES (ralos, grilla de fin de trimestre)
# → ind_fundamental_quarterly. Todos num (FLOAT).
_WIDE_FUND_DAILY = [
    "fundamental_pe_ttm", "fundamental_pb", "fundamental_ps_ttm",
    "fundamental_pe_growth_yoy",
]
_WIDE_FUND_QUARTERLY = [
    "fundamental_net_margin", "fundamental_gross_margin",
    "fundamental_operating_margin", "fundamental_debt_to_equity",
    "fundamental_revenue_growth_yoy", "fundamental_eps_growth_yoy",
    "fundamental_net_income_growth_yoy", "fundamental_roic",
]
# Columnas categóricas (VARCHAR(50)); el resto son FLOAT.
_WIDE_STR_CODES = frozenset({
    "trend_daily", "trend_weekly", "trend_monthly",
    "volatility_daily", "volatility_weekly", "volatility_monthly",
})

_WIDE_CADENCE_COLUMNS = {
    "daily": _WIDE_DAILY, "weekly": _WIDE_WEEKLY, "monthly": _WIDE_MONTHLY,
    "fund_daily": _WIDE_FUND_DAILY, "fund_quarterly": _WIDE_FUND_QUARTERLY,
}
_WIDE_CADENCE_TABLE = {
    "daily": "ind_daily", "weekly": "ind_weekly", "monthly": "ind_monthly",
    "fund_daily": "ind_fundamental_daily",
    "fund_quarterly": "ind_fundamental_quarterly",
}

# code -> (tabla_ancha, columna, cadencia). Fuente única de la clasificación de
# cadencia de los indicadores técnicos con historia.
_WIDE: dict[str, tuple[str, str, str]] = {
    code: (_WIDE_CADENCE_TABLE[cad], code, cad)
    for cad, codes in _WIDE_CADENCE_COLUMNS.items()
    for code in codes
}


def use_wide_ind_tables() -> bool:
    """Ruteo a tablas anchas (docs/notes/design_ind_wide_tables.md). Default
    TRUE desde la fase 5: las per-código de los códigos _WIDE se dropearon
    (migración 0079), así que wide es el camino permanente. Se puede forzar
    per-código con USE_WIDE_IND_TABLES=0 (debug, o bases aún sin migrar/poblar
    las anchas). La suite lo pone en 0 en conftest (los tests usan sqlite y
    tablas per-código); los tests de wide lo vuelven a 1."""
    return os.environ.get("USE_WIDE_IND_TABLES", "1").strip().lower() in (
        "1", "true", "yes", "on")


def _get_wide_table(name: str) -> Table:
    """Refleja ind_daily/ind_weekly/ind_monthly desde la BD (mismo caché de
    MetaData que get_ind_table). resolve_fks=False: no refleja la tabla assets
    referenciada por el FK (no hace falta para las lecturas, y evita depender de
    su presencia)."""
    if name in _meta.tables and len(_meta.tables[name].columns) > 0:
        return _meta.tables[name]
    with _meta_lock:
        if name in _meta.tables and len(_meta.tables[name].columns) > 0:
            return _meta.tables[name]
        return Table(name, _meta, autoload_with=engine, resolve_fks=False,
                     extend_existing=True)


class _CodeColumns:
    """Emula el `.c` de una tabla ind_{code} per-código sobre una columna de la
    tabla ancha: value/date/asset_id son los Column REALES de la tabla ancha,
    así cualquier select/where/join compila directo contra ella (SQL plano, sin
    subquery). Iterable como (asset_id, date, value) para los lectores que
    recorren las columnas (p.ej. data_explorer)."""

    __slots__ = ("value", "date", "asset_id", "_cols")

    def __init__(self, wide: Table, column: str):
        self.value    = wide.c[column]
        self.date     = wide.c.date
        self.asset_id = wide.c.asset_id
        self._cols    = (self.asset_id, self.date, self.value)

    def __iter__(self):
        return iter(self._cols)


class _CodeView:
    """Vista por-código sobre una tabla ancha (design_ind_wide_tables.md):
    drop-in de una tabla ind_{code} para los LECTORES. `.c.value` es la columna
    del código en la ancha; `.name`, el nombre de la ancha; `.join` delega en la
    ancha. Los escritores NO la usan (usan technical_service.upsert_ind_cadence)."""

    __slots__ = ("c", "columns", "name", "_wide")

    def __init__(self, wide: Table, column: str):
        self.c       = _CodeColumns(wide, column)
        self.columns = self.c
        self.name    = wide.name
        self._wide   = wide

    def join(self, *args, **kwargs):
        return self._wide.join(*args, **kwargs)


def get_ind_table(code: str) -> Table:
    """Tabla de un indicador para los lectores. Con el flag de tablas anchas
    (use_wide_ind_tables) y un código mapeado en _WIDE devuelve un _CodeView
    sobre ind_{cadencia}; si no, refleja la ind_{code} per-código desde la BD
    (caché interno de MetaData)."""
    if use_wide_ind_tables() and code in _WIDE:
        table_name, column, _cad = _WIDE[code]
        return _CodeView(_get_wide_table(table_name), column)
    name = f"ind_{code}"
    # Fast path: tabla ya reflejada con columnas
    if name in _meta.tables and len(_meta.tables[name].columns) > 0:
        return _meta.tables[name]
    # Slow path: un solo thread refleja a la vez para evitar race condition
    with _meta_lock:
        if name in _meta.tables and len(_meta.tables[name].columns) > 0:
            return _meta.tables[name]
        return Table(name, _meta, autoload_with=engine, extend_existing=True)


def ensure_ind_table(code: str, ind_type: str = "num", bind=None) -> None:
    """Crea ind_{code} si no existe. Las tablas por indicador no forman
    parte de Base.metadata (get_ind_table las refleja de la BD), así que
    una base nacida por create_all + stamp head (scripts/init_db.py) no
    las trae — esta función las materializa desde IndicatorDefinition en
    el arranque (ensure_builtin_data). En una base con historia (creada
    por las migraciones 0043/0060) es solo una inspección.

    Esquema idéntico al de la migración 0043 (PK (asset_id, date), FK a
    assets con CASCADE, value Float o String(50) según ind_type) más el
    índice por date de la 0062. Se construye en un MetaData efímero para
    no interferir con el caché de autoload de get_ind_table."""
    import sqlalchemy as sa

    b = bind or engine
    name = f"ind_{code}"
    if sa.inspect(b).has_table(name):
        return
    tmp = MetaData()
    # stub de assets solo para que el FK compile — no se crea (tables=[t])
    Table("assets", tmp, Column("id", Integer, primary_key=True))
    vcol = (Column("value", String(50), nullable=True) if ind_type == "str"
            else Column("value", Float, nullable=True))
    t = Table(
        name, tmp,
        Column("asset_id", Integer,
               ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
        Column("date", Date, nullable=False),
        vcol,
        PrimaryKeyConstraint("asset_id", "date"),
        Index(f"ix_{name}_date", "date"),
    )
    tmp.create_all(b, tables=[t])


def ensure_wide_ind_tables(bind=None) -> None:
    """Crea ind_daily/ind_weekly/ind_monthly si no existen. Igual que
    ensure_ind_table para las ind_{code} per-código: no forman parte de
    Base.metadata, así que una base nacida por create_all + stamp head no las
    trae — ensure_builtin_data las materializa en el arranque. En una base
    migrada (0077) ya existen y esto es una inspección por tabla.

    Esquema idéntico al de la migración 0077: PK (asset_id, date), FK a assets
    con CASCADE, ix_date, una columna por code (VARCHAR(50) para trend_*/
    volatility_*, Float el resto), todas nullable."""
    import sqlalchemy as sa

    b = bind or engine
    for cadence, table_name in _WIDE_CADENCE_TABLE.items():
        if sa.inspect(b).has_table(table_name):
            continue
        tmp = MetaData()
        # stub de assets solo para que el FK compile — no se crea (tables=[t])
        Table("assets", tmp, Column("id", Integer, primary_key=True))
        cols = [
            Column("asset_id", Integer,
                   ForeignKey("assets.id", ondelete="CASCADE"), nullable=False),
            Column("date", Date, nullable=False),
        ]
        for code in _WIDE_CADENCE_COLUMNS[cadence]:
            # Float(precision=24) = precisión simple: en PostgreSQL materializa
            # REAL (4 B) en vez de double precision (8 B) — la mitad del footprint
            # numérico. En MySQL FLOAT(24) es idéntico al FLOAT histórico (ya 4 B):
            # neutral al motor. Ver migración 0087 (ALTER de bases existentes) y
            # docs/notes/design_ind_wide_tables.md. Los valores (RSI, distancias %,
            # retornos, percentiles) tienen 2-4 dígitos útiles; float4 da ~7.
            ctype = String(50) if code in _WIDE_STR_CODES else Float(precision=24)
            cols.append(Column(code, ctype, nullable=True))
        t = Table(
            table_name, tmp, *cols,
            PrimaryKeyConstraint("asset_id", "date"),
            Index(f"ix_{table_name}_date", "date"),
        )
        tmp.create_all(b, tables=[t])


# Lookup "as-of": máxima antigüedad aceptada del último valor. Los
# indicadores semanales/mensuales se guardan con fechas de fin de período
# (el resample etiqueta las semanas en domingo), así que una fecha diaria
# arbitraria no tiene fila exacta. El tope evita levantar valores zombie de
# activos que dejaron de cotizar (45 días cubre etiquetas mensuales +
# feriados largos).
ASOF_MAX_LOOKBACK_DAYS = 45


def query_values_asof(session, code: str, target_date) -> dict[int, object]:
    """{asset_id: value} con la última fila de ind_{code} <= target_date por
    activo (ver ASOF_MAX_LOOKBACK_DAYS). Usado por signal_service y por el
    filtro de elegibilidad de estrategias — un match exacto de fecha dejaría
    sin valor a los indicadores semanales/mensuales casi cualquier día."""
    from datetime import timedelta

    import sqlalchemy as sa

    tbl = get_ind_table(code)
    cutoff = target_date - timedelta(days=ASOF_MAX_LOOKBACK_DAYS)
    # value IS NOT NULL: as-of POR COLUMNA (fiel). En una tabla ancha la fila de
    # una fecha existe aunque ESTA columna sea NULL (la escribió otro código de
    # la cadencia); sin el filtro ese NULL ganaría el MAX(date) y ocultaría el
    # último valor válido del código. En las ind_{code} per-código (que nunca
    # guardan value NULL) es equivalente al comportamiento previo.
    latest = (
        sa.select(tbl.c.asset_id, sa.func.max(tbl.c.date).label("mx"))
        .where(tbl.c.date <= target_date, tbl.c.date >= cutoff,
               tbl.c.value.isnot(None))
        .group_by(tbl.c.asset_id)
        .subquery()
    )
    rows = session.execute(
        sa.select(tbl.c.asset_id, tbl.c.value)
        .select_from(tbl.join(
            latest,
            sa.and_(tbl.c.asset_id == latest.c.asset_id,
                    tbl.c.date == latest.c.mx),
        ))
    ).fetchall()
    return {aid: v for aid, v in rows if v is not None}


class CurrentIndicatorValue(Base):
    """Indicadores sin historia (keep_history=False): un valor vigente por activo."""

    __tablename__ = "current_indicator_values"

    asset_id  = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    code      = Column(String(50), primary_key=True)
    value_num = Column(Float,      nullable=True)
    value_str = Column(String(50), nullable=True)


class IndAssetMeta(Base):
    """Metadato de invalidación/caché por activo e indicador: referencia
    externa (benchmark_id, ver _BENCHMARK_DEP_CODES) o hash del prefijo
    histórico (checksum, ver _CHECKSUM_DEP_CODES) usados en el último
    cálculo completo de la serie, para detectar cuándo el camino rápido
    del delta debe invalidarse aunque no haya huecos en el historial
    guardado. min_date/max_date/row_count cachean el resultado de
    _query_tail_stats (evita un full-scan de ind_{code} en cada delta) y
    se recalculan en cada backfill_indicator exitoso — ver
    _upsert_ind_stats_meta y el DELETE junto al TRUNCATE en force.

    Nota: la consola SQL de administración permite DML arbitrario sobre
    ind_* sin pasar por estos servicios. Si se edita una tabla ind_{code}
    a mano ahí, este caché (y benchmark_id/checksum) puede quedar
    desincronizado — forzar un rebuild (force=True) de ese indicador
    después de cualquier edición manual."""

    __tablename__ = "ind_asset_meta"

    asset_id     = Column(Integer, ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True)
    code         = Column(String(50), primary_key=True)
    benchmark_id = Column(Integer, nullable=True)
    checksum     = Column(String(64), nullable=True)
    min_date     = Column(Date, nullable=True)
    max_date     = Column(Date, nullable=True)
    row_count    = Column(Integer, nullable=True)
