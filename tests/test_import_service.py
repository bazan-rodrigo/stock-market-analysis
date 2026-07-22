"""import_service: helpers puros de validación/reconciliación de datos
importados + la orquestación del import en dos fases (validación de red en
paralelo → alta en BD secuencial) contra el stub sqlite y fuentes de mentira.
La descarga real contra Yahoo vive en el Codespace."""
import sys
import types
from types import SimpleNamespace

import pytest

from app.database import Base, engine, get_session
from app.services import import_service as svc
from app.services.import_service import (
    TEMPLATE_COLUMNS,
    _cached_resolve,
    _first_nonempty,
    _is_transient_error,
    _needs_metadata,
    _prefetch_validations,
    _row_ticker,
    _valid,
    _validate_with_retry,
)


# ── _valid ────────────────────────────────────────────────────────────────────

def test_valid_string_normal_es_valido():
    assert _valid("Argentina") is True


def test_valid_vacio_o_none_es_invalido():
    assert _valid("") is False
    assert _valid(None) is False


def test_valid_nan_none_string_case_insensitive_es_invalido():
    assert _valid("nan") is False
    assert _valid("NaN") is False
    assert _valid("None") is False
    assert _valid("  nan  ") is False


def test_valid_solo_espacios_es_invalido():
    assert _valid("   ") is False


def test_valid_cero_numerico_es_invalido():
    # bool(0) es False: un valor numérico 0 se trata como "vacío", no como dato
    assert _valid(0) is False
    assert _valid(0.0) is False


# ── _first_nonempty ───────────────────────────────────────────────────────────

def test_first_nonempty_devuelve_el_primero_valido():
    assert _first_nonempty(None, "nan", "  ", "Argentina", "Brasil") == "Argentina"


def test_first_nonempty_recorta_espacios():
    assert _first_nonempty("  Chile  ") == "Chile"


def test_first_nonempty_todos_invalidos_devuelve_vacio():
    assert _first_nonempty(None, "nan", "None", "") == ""


def test_first_nonempty_sin_argumentos_devuelve_vacio():
    assert _first_nonempty() == ""


def test_first_nonempty_cero_numerico_se_saltea():
    # 0 es falsy → se saltea igual que un valor vacío, aunque sea un dato real
    assert _first_nonempty(0, "Uruguay") == "Uruguay"


# ── Fakes compartidos ─────────────────────────────────────────────────────────

class _Res:
    def __init__(self, valid=True, error=None, metadata=None):
        self.valid = valid
        self.error = error
        self.metadata = metadata


class _FakeSource:
    """Fuente de mentira: registra llamadas y responde según guion.

    script: lista de resultados/exceptions consumida en orden (para tests de
    un solo ticker — con varios el orden del pool no es determinista).
    by_ticker: respuesta fija por ticker (determinista bajo paralelismo).
    """

    def __init__(self, script=None, by_ticker=None):
        self.calls = []  # [(ticker, need_metadata)]
        self.script = list(script or [])
        self.by_ticker = dict(by_ticker or {})

    def validate_ticker(self, ticker, need_metadata=True):
        self.calls.append((ticker, need_metadata))
        if ticker in self.by_ticker:
            item = self.by_ticker[ticker]
        elif self.script:
            item = self.script.pop(0)
        else:
            item = _Res()
        if isinstance(item, Exception):
            raise item
        return item


def _fila_completa(ticker="AAA", fuente="Fake", **extra):
    """Fila con todos los campos autocompletables → no necesita metadata."""
    row = {
        "ticker": ticker, "fuente_precios": fuente, "nombre": "Empresa SA",
        "pais_iso": "US", "mercado": "NYSE", "moneda": "Dolar EEUU",
        "tipo_instrumento": "EQUITY", "sector": "Tecnologia",
        "industria": "Software",
    }
    row.update(extra)
    return row


@pytest.fixture()
def fake_registry(monkeypatch):
    """Suplanta app.sources.registry ANTES de que el import diferido lo
    cargue (el real importa yfinance, que no está en esta PC)."""
    mod = types.ModuleType("app.sources.registry")
    sources = {}
    mod.get_source = lambda name: sources[name]
    monkeypatch.setitem(sys.modules, "app.sources.registry", mod)
    return sources


# ── _needs_metadata ───────────────────────────────────────────────────────────

def test_needs_metadata_falso_con_fila_completa():
    assert _needs_metadata(_fila_completa()) is False


def test_needs_metadata_verdadero_si_falta_un_campo():
    assert _needs_metadata(_fila_completa(sector="")) is True


def test_needs_metadata_nan_cuenta_como_faltante():
    assert _needs_metadata(_fila_completa(moneda="nan")) is True


def test_needs_metadata_columna_ausente_cuenta_como_faltante():
    row = _fila_completa()
    del row["industria"]
    assert _needs_metadata(row) is True


# ── _is_transient_error ───────────────────────────────────────────────────────

def test_transitorio_rate_limit_y_red():
    assert _is_transient_error("Rate limit de Yahoo Finance (HTTP 429)") is True
    assert _is_transient_error("HTTPSConnectionPool: Read timed out") is True
    assert _is_transient_error("Connection reset by peer") is True


def test_no_transitorio_ticker_inexistente_o_vacio():
    assert _is_transient_error("Ticker no encontrado en Yahoo Finance") is False
    assert _is_transient_error(None) is False
    assert _is_transient_error("") is False


# ── _validate_with_retry ──────────────────────────────────────────────────────

def test_retry_reintenta_transitorio_y_devuelve_el_exito(monkeypatch):
    sleeps = []
    monkeypatch.setattr(svc.time, "sleep", sleeps.append)
    src = _FakeSource(script=[_Res(False, "HTTP 429"), _Res(True)])
    out = _validate_with_retry(src, "AAA", need_metadata=True)
    assert out.valid is True
    assert len(src.calls) == 2
    assert len(sleeps) == 1


def test_retry_error_permanente_no_reintenta(monkeypatch):
    monkeypatch.setattr(svc.time, "sleep",
                        lambda s: pytest.fail("no debe dormir sin reintento"))
    src = _FakeSource(script=[_Res(False, "Ticker no encontrado en Yahoo Finance")])
    out = _validate_with_retry(src, "AAA", need_metadata=True)
    assert out.valid is False
    assert len(src.calls) == 1


def test_retry_agota_reintentos_con_backoff_creciente(monkeypatch):
    sleeps = []
    monkeypatch.setattr(svc.time, "sleep", sleeps.append)
    src = _FakeSource(script=[_Res(False, "timeout")] * 5)
    out = _validate_with_retry(src, "AAA", need_metadata=True)
    assert out.valid is False
    assert len(src.calls) == 1 + svc._VALIDATE_RETRIES
    assert len(sleeps) == svc._VALIDATE_RETRIES
    assert sleeps == sorted(sleeps) and sleeps[-1] > sleeps[0]  # exponencial


def test_retry_conserva_need_metadata(monkeypatch):
    monkeypatch.setattr(svc.time, "sleep", lambda s: None)
    src = _FakeSource(script=[_Res(False, "429"), _Res(True)])
    _validate_with_retry(src, "AAA", need_metadata=False)
    assert src.calls == [("AAA", False), ("AAA", False)]


# ── _row_ticker ───────────────────────────────────────────────────────────────

def test_row_ticker_normaliza_a_mayusculas():
    assert _row_ticker({"ticker": "  aapl "}) == "AAPL"


def test_row_ticker_filas_vacias_y_separadores():
    assert _row_ticker({}) == ""
    assert _row_ticker({"ticker": None}) == ""
    assert _row_ticker({"ticker": "── Sección ──"}) == ""
    assert _row_ticker({"ticker": "--- corte ---"}) == ""


# ── _prefetch_validations ─────────────────────────────────────────────────────

def test_prefetch_dedup_salteos_y_sin_metadata(fake_registry):
    src = _FakeSource()
    fake_registry["Fake"] = src
    rows = [
        _fila_completa("aaa"),                       # se valida (normalizada)
        _fila_completa("AAA"),                       # duplicada en el archivo
        _fila_completa("EXIST"),                     # ya está en la base
        _fila_completa("BBB", fuente="Desconocida"),  # fuente inválida
        {"ticker": "", "fuente_precios": "Fake"},    # fila vacía
    ]
    out = _prefetch_validations(rows, {"Fake": object()}, {"EXIST"})
    assert list(out) == [("Fake", "AAA")]
    # una sola llamada de red, sin metadata (la fila está completa)
    assert src.calls == [("AAA", False)]


def test_prefetch_pide_metadata_si_alguna_fila_del_ticker_la_necesita(fake_registry):
    src = _FakeSource()
    fake_registry["Fake"] = src
    completa   = _fila_completa("CCC")
    incompleta = {"ticker": "CCC", "fuente_precios": "Fake"}
    _prefetch_validations([completa, incompleta], {"Fake": 1}, set())
    assert src.calls == [("CCC", True)]


def test_prefetch_sin_trabajo_devuelve_vacio_sin_tocar_la_red():
    # Sin stub del registry: todo salteado → jamás llega al import diferido
    out = _prefetch_validations([_fila_completa("EXIST")], {"Fake": 1}, {"EXIST"})
    assert out == {}


def test_prefetch_excepcion_se_vuelve_resultado_invalido(fake_registry):
    fake_registry["Fake"] = _FakeSource(
        by_ticker={"DDD": RuntimeError("se rompió la red")})
    out = _prefetch_validations([_fila_completa("DDD")], {"Fake": 1}, set())
    res = out[("Fake", "DDD")]
    assert res.valid is False
    assert "se rompió la red" in res.error


def test_prefetch_reporta_progreso_de_validacion(fake_registry):
    fake_registry["Fake"] = _FakeSource()
    ticks = []
    _prefetch_validations(
        [_fila_completa("EEE"), _fila_completa("FFF")], {"Fake": 1}, set(),
        progress_cb=lambda c, t, msg="": ticks.append((c, t, msg)))
    assert sorted(t[:2] for t in ticks) == [(1, 2), (2, 2)]
    assert all(t[2] == "Validando tickers..." for t in ticks)


def test_prefetch_fuente_en_bd_sin_implementacion_no_voltea_el_resto(fake_registry):
    # "Fake" está registrada; "SinImpl" está en price_sources (existe en la
    # tabla PriceSource) pero NO en el registry → get_source lanza. El
    # prefetch NO debe abortar: saltea ese job y valida el resto.
    fake_registry["Fake"] = _FakeSource()
    rows = [
        _fila_completa("AAA", fuente="Fake"),
        _fila_completa("BBB", fuente="SinImpl"),
    ]
    out = _prefetch_validations(rows, {"Fake": 1, "SinImpl": 1}, set())
    assert ("Fake", "AAA") in out          # la fuente válida se validó
    assert ("SinImpl", "BBB") not in out   # la sin implementación se salteó
    assert out[("Fake", "AAA")].valid is True


def test_prefetch_progreso_cuadra_cuando_se_saltea_una_fuente(fake_registry):
    # Con un job salteado, el denominador del progreso debe contar solo los
    # jobs realmente validados (no quedar en 1/2 para siempre).
    fake_registry["Fake"] = _FakeSource()
    ticks = []
    _prefetch_validations(
        [_fila_completa("AAA", fuente="Fake"),
         _fila_completa("BBB", fuente="SinImpl")],
        {"Fake": 1, "SinImpl": 1}, set(),
        progress_cb=lambda c, t, msg="": ticks.append((c, t)))
    assert ticks == [(1, 1)]


# ── _cached_resolve ───────────────────────────────────────────────────────────

def test_cached_resolve_memoiza_case_insensitive():
    calls, cache = [], {}

    def fn(value):
        calls.append(value)
        return 42

    assert _cached_resolve(cache, "sector", "Tech", fn) == 42
    assert _cached_resolve(cache, "sector", "  tech ", fn) == 42
    assert calls == ["Tech"]


def test_cached_resolve_distingue_args_extra():
    calls, cache = [], {}

    def fn(value, sector_id=None):
        calls.append((value, sector_id))
        return len(calls)

    a = _cached_resolve(cache, "industry", "Software", fn, 1)
    b = _cached_resolve(cache, "industry", "Software", fn, 2)
    assert (a, b) == (1, 2)  # misma industria bajo sectores distintos: 2 entradas


def test_cached_resolve_cachea_tambien_none():
    calls, cache = [], {}

    def fn(value):
        calls.append(value)
        return None

    assert _cached_resolve(cache, "country", "nan", fn) is None
    assert _cached_resolve(cache, "country", "nan", fn) is None
    assert calls == ["nan"]


# ── import_from_excel de punta a punta (stub sqlite + fuente de mentira) ─────

_E2E = "IMPE2E"


def _xlsx(rows) -> bytes:
    import openpyxl
    from io import BytesIO
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(TEMPLATE_COLUMNS)
    for r in rows:
        ws.append([r.get(c, "") for c in TEMPLATE_COLUMNS])
    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()


@pytest.fixture()
def db_import():
    import app.models  # noqa: F401 — registra los modelos en Base.metadata
    Base.metadata.create_all(engine)
    s = get_session()
    s.query(svc.Asset).filter(svc.Asset.ticker.like(f"{_E2E}%")).delete(
        synchronize_session=False)
    s.query(svc.ImportLog).filter(svc.ImportLog.ticker.like(f"{_E2E}%")).delete(
        synchronize_session=False)
    ps = s.query(svc.PriceSource).filter_by(name="FakeE2E").first()
    if ps is None:
        ps = svc.PriceSource(name="FakeE2E")
        s.add(ps)
    s.commit()
    yield s
    s.rollback()


def test_import_e2e_dos_fases(db_import, fake_registry):
    s = db_import
    # Activo preexistente: la fila del archivo debe saltearse SIN red
    if not s.query(svc.Asset).filter_by(ticker=f"{_E2E}X").first():
        s.add(svc.Asset(ticker=f"{_E2E}X", name="ya estaba",
                        price_source_id=s.query(svc.PriceSource)
                                          .filter_by(name="FakeE2E").first().id))
        s.commit()

    meta = SimpleNamespace(
        name="Autocompletada SA", sector="AutoSector", industry="AutoIndustria",
        currency_iso="USD", exchange="NYQ", exchange_name="NYSE",
        country="Estados Unidos", quote_type="EQUITY")
    src = _FakeSource(by_ticker={
        f"{_E2E}B": _Res(metadata=meta),
        f"{_E2E}D": _Res(False, "Ticker no encontrado en Yahoo Finance"),
    })
    fake_registry["FakeE2E"] = src

    rows = [
        # completa, con benchmark que se crea DESPUÉS (referencia adelantada)
        _fila_completa(f"{_E2E}A", fuente="FakeE2E",
                       benchmark_ticker=f"{_E2E}B"),
        {"ticker": f"{_E2E}B", "fuente_precios": "FakeE2E"},   # autocompleta
        _fila_completa(f"{_E2E}A", fuente="FakeE2E"),          # duplicada
        _fila_completa(f"{_E2E}C", fuente="NoExiste"),         # fuente mala
        {"ticker": f"{_E2E}D", "fuente_precios": "FakeE2E"},   # inválido
        _fila_completa(f"{_E2E}X", fuente="FakeE2E"),          # ya en la base
    ]
    progreso = []
    results = svc.import_from_excel(
        _xlsx(rows), progress_cb=lambda c, t, msg="": progreso.append(msg))

    by_ticker = {}
    for r in results:
        by_ticker.setdefault(r["ticker"], []).append(r)

    assert by_ticker[f"{_E2E}A"][0]["status"] == "imported"
    # sin advertencia espuria por fuente_fundamentales vacía (NaN del Excel)
    assert by_ticker[f"{_E2E}A"][0]["detail"] == "Importado correctamente"
    assert by_ticker[f"{_E2E}A"][1]["status"] == "skipped"     # dup en archivo
    assert by_ticker[f"{_E2E}B"][0]["status"] == "imported"
    assert by_ticker[f"{_E2E}C"][0]["status"] == "error"
    assert "Fuente" in by_ticker[f"{_E2E}C"][0]["detail"]
    assert by_ticker[f"{_E2E}D"][0]["status"] == "error"
    assert "inválido" in by_ticker[f"{_E2E}D"][0]["detail"]
    assert by_ticker[f"{_E2E}X"][0]["status"] == "skipped"

    # Red: A completa → sin metadata; B incompleta → con metadata; X jamás
    calls = dict(src.calls)
    assert calls[f"{_E2E}A"] is False
    assert calls[f"{_E2E}B"] is True
    assert f"{_E2E}X" not in calls
    assert len(src.calls) == 3  # A, B, D — una sola vez cada uno

    # Alta y autocompletado
    a = s.query(svc.Asset).filter_by(ticker=f"{_E2E}A").first()
    b = s.query(svc.Asset).filter_by(ticker=f"{_E2E}B").first()
    assert a is not None and b is not None
    assert b.name == "Autocompletada SA"
    assert b.sector_id is not None          # creado desde la metadata
    assert a.benchmark_id == b.id           # 2da pasada resolvió la referencia

    # Logs persistidos. El log guarda el ÚLTIMO intento por ticker (semántica
    # histórica del upsert por fila): la fila duplicada de A pisa su
    # "imported" con "skipped" dentro de la misma corrida.
    logs = {l.ticker: l for l in s.query(svc.ImportLog)
            .filter(svc.ImportLog.ticker.like(f"{_E2E}%")).all()}
    assert logs[f"{_E2E}A"].status == "skipped"
    assert logs[f"{_E2E}B"].status == "imported"
    assert logs[f"{_E2E}D"].status == "error"

    # Progreso en dos fases
    assert "Validando tickers..." in progreso
    assert "Importando..." in progreso


def test_import_e2e_benchmark_inexistente_anota_advertencia(db_import, fake_registry):
    s = db_import
    fake_registry["FakeE2E"] = _FakeSource()
    rows = [_fila_completa(f"{_E2E}W", fuente="FakeE2E",
                           benchmark_ticker=f"{_E2E}NOEXISTE")]
    results = svc.import_from_excel(_xlsx(rows))
    assert results[0]["status"] == "imported"
    assert "no encontrado" in results[0]["detail"]
    w = s.query(svc.Asset).filter_by(ticker=f"{_E2E}W").first()
    assert w.benchmark_id is None
    log = s.query(svc.ImportLog).filter_by(ticker=f"{_E2E}W").first()
    assert "no encontrado" in log.detail


def test_import_e2e_fuente_sin_implementacion_no_aborta_el_archivo(db_import, fake_registry):
    # Regresión: una fuente en la tabla PriceSource pero sin implementación en
    # el registry (dada de alta/renombrada desde el ABM) hacía explotar el
    # import ENTERO en la fase 1 (0 filas, 0 logs). Ahora esa fila queda en
    # error y el resto del archivo se importa igual.
    s = db_import
    if not s.query(svc.PriceSource).filter_by(name="SinImplE2E").first():
        s.add(svc.PriceSource(name="SinImplE2E"))
        s.commit()
    fake_registry["FakeE2E"] = _FakeSource()   # SinImplE2E NO se registra

    rows = [
        _fila_completa(f"{_E2E}OK", fuente="FakeE2E"),
        _fila_completa(f"{_E2E}BAD", fuente="SinImplE2E"),
    ]
    results = svc.import_from_excel(_xlsx(rows))

    by_ticker = {r["ticker"]: r for r in results}
    assert by_ticker[f"{_E2E}OK"]["status"] == "imported"   # el resto NO se cae
    assert by_ticker[f"{_E2E}BAD"]["status"] == "error"
    # el activo válido quedó creado y su log persistido
    assert s.query(svc.Asset).filter_by(ticker=f"{_E2E}OK").first() is not None
    assert s.query(svc.ImportLog).filter_by(ticker=f"{_E2E}BAD").first().status == "error"
