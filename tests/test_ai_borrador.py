"""Estrategias que no existen: medirlas sin crearlas, y las dos defensas.

Lo que motivó todo esto: con la base recién instalada —señales calculadas pero
ninguna estrategia creada todavía— la IA no tenía **nada** que medir. Las dos
herramientas de backtest pedían una estrategia materializada, así que lo único
que podía hacer era proponer ideas de memoria. Estos tests fijan que ahora una
estrategia entera viaje en la llamada y se mida contra la historia real sin
crear absolutamente nada.

La otra mitad son las defensas contra el sobreajuste (`app/ai/prudencia.py`).
Que probar salga gratis es justo lo que hace peligroso al sobreajuste: con
suficientes intentos siempre aparece una combinación que se ve excelente por
casualidad. Los tests de holdout fijan lo que hace que la reserva signifique
algo — que el tramo se EXCLUYA del cómputo (no que se oculte del resultado) y
que el corte no dependa de lo que pidió la llamada.
"""
import datetime

import pytest
import sqlalchemy as sa

from app.ai import prudencia, registry
from app.ai.caller import AiCaller
from app.database import Base, Session, engine, get_session

_ADMIN, _ANA = 1, 7


@pytest.fixture()
def db():
    import app.models  # noqa: F401

    Session.remove()
    Base.metadata.create_all(engine)
    tablas = ("strategy_component", "strategy", "`signal`", "prices", "assets")
    anchas = ("signal_values_wide", "strategy_results_wide")

    def _limpiar(conn):
        for t in tablas:
            conn.execute(sa.text(f"DELETE FROM {t}"))
        for t in anchas:
            if sa.inspect(conn).has_table(t):
                conn.execute(sa.text(f"DELETE FROM {t}"))

    def _dropear_dinamicas():
        from app.models import signal_store

        sig, strat = signal_store._list_dynamic_tables()
        nombres = list(sig.values()) + list(strat.values())
        with engine.begin() as conn:
            for n in nombres:
                conn.execute(sa.text(f"DROP TABLE IF EXISTS {n}"))
        for n in nombres:
            if n in signal_store._meta.tables:
                signal_store._meta.remove(signal_store._meta.tables[n])

    _dropear_dinamicas()
    with engine.begin() as conn:
        _limpiar(conn)
    prudencia.reiniciar_contador()
    yield
    Session.remove()
    _dropear_dinamicas()
    with engine.begin() as conn:
        _limpiar(conn)
    Session.remove()
    prudencia.reiniciar_contador()


_N_ACTIVOS = 24
_N_FECHAS = 40
_D0 = datetime.date(2024, 1, 1)


def _mundo(n_activos=_N_ACTIVOS, n_fechas=_N_FECHAS):
    """Señales con historia y precios, y NINGUNA estrategia — que es el punto.

    24 activos y no 2: el IC es una correlación y el mínimo de observaciones
    por fecha del backtest es 20, así que un mundo chico haría pasar los tests
    por vacuidad en vez de por lo que dicen medir.
    """
    from app.models import Asset, Price, SignalDefinition, signal_store

    s = get_session()
    activos = [Asset(ticker=f"B{i:03d}", name=f"B{i}", price_source_id=1)
               for i in range(n_activos)]
    s.add_all(activos)
    sig_a = SignalDefinition(key="sig_a", name="A", formula_type="threshold",
                             params="{}", owner_id=_ADMIN, is_public=True)
    sig_b = SignalDefinition(key="sig_b", name="B", formula_type="threshold",
                             params="{}", owner_id=_ADMIN, is_public=True)
    s.add_all([sig_a, sig_b])
    s.commit()

    fechas = [_D0 + datetime.timedelta(days=d) for d in range(n_fechas)]
    for i, a in enumerate(activos):
        for t_i, f in enumerate(fechas):
            s.add(Price(asset_id=a.id, date=f,
                        close=100.0 + i * 0.5 + t_i * (1 + (i % 7) * 0.1)))
    s.commit()

    signal_store.ensure_signal_storage(sig_a.id)
    signal_store.ensure_signal_storage(sig_b.id)

    valores = {activos[i].id: (i - n_activos // 2) * 8.0
               for i in range(n_activos)}
    for sig_id, signo in ((sig_a.id, 1.0), (sig_b.id, -1.0)):
        rt = signal_store.read_sig_table(s, sig_id)
        s.execute(rt.insert(), [
            {"date": f, "asset_id": aid, "score": v * signo}
            for f in fechas for aid, v in valores.items()])
    s.commit()
    return [a.id for a in activos], fechas


# ── Medir sin estrategia ─────────────────────────────────────────────────────

def test_mide_una_estrategia_que_no_existe(db):
    """LO CENTRAL. Sin una sola estrategia en la base, un juego de componentes
    se puntúa contra la historia real y devuelve IC y cuantiles."""
    from app.models import Strategy
    from app.services import backtest_service

    _mundo()
    assert get_session().query(Strategy).count() == 0

    out = backtest_service.compute_draft_backtest(
        [{"signal_key": "sig_a", "weight": 1}], None, {"horizons": [1]})

    assert out["n_dates"] > 0
    assert out["quantile_stats"]


def test_el_borrador_no_escribe_nada(db):
    """Ni estrategia, ni componentes, ni corrida guardada."""
    from app.models import BacktestRun, Strategy, StrategyComponent
    from app.services import backtest_service

    _mundo()
    backtest_service.compute_draft_backtest(
        [{"signal_key": "sig_a", "weight": 1}], None, {"horizons": [1]})
    Session.remove()

    s = get_session()
    assert s.query(Strategy).count() == 0
    assert s.query(StrategyComponent).count() == 0
    assert s.query(BacktestRun).count() == 0


def test_el_peso_negativo_invierte_el_borrador(db):
    """Con una sola señal, pesar −1 da el IC opuesto al de +1: la prueba de que
    el borrador usa la MISMA semántica de score que el motor real, divisor en
    valor absoluto incluido."""
    from app.services import backtest_service

    _mundo()
    cfg = {"horizons": [1]}
    mas = backtest_service.compute_draft_backtest(
        [{"signal_key": "sig_a", "weight": 1}], None, cfg)
    menos = backtest_service.compute_draft_backtest(
        [{"signal_key": "sig_a", "weight": -1}], None, cfg)

    ic_mas = [p["ic"] for p in mas["ic_points"] if p["ic"] is not None]
    ic_menos = [p["ic"] for p in menos["ic_points"] if p["ic"] is not None]
    assert ic_mas and len(ic_mas) == len(ic_menos)
    for a, b in zip(ic_mas, ic_menos):
        assert a == pytest.approx(-b, abs=1e-9)


def test_el_filtro_de_elegibilidad_recorta_el_universo(db):
    """El filtro del borrador es el mismo motor del pipeline, evaluado fecha
    por fecha: si excluye activos, el ranking tiene menos observaciones."""
    import json

    from app.models import Asset
    from app.services import backtest_service

    ids, _fechas = _mundo()
    s = get_session()
    # La mitad de los activos a un sector, para filtrar por atributo (no
    # depende de indicadores, así que el test no necesita tablas ind_*).
    for aid in ids[:12]:
        s.query(Asset).filter(Asset.id == aid).update({"sector_id": 3})
    s.commit()

    filtro = json.dumps({"op": "AND", "children": [
        {"cond": {"left": {"type": "attribute", "key": "sector"},
                  "operator": "=",
                  "right": {"type": "const", "value": 3}}}]})

    sin = backtest_service.draft_score_rows(
        [{"signal_key": "sig_a", "weight": 1}], None, {"horizons": [1]})
    con = backtest_service.draft_score_rows(
        [{"signal_key": "sig_a", "weight": 1}], filtro, {"horizons": [1]})

    activos_sin = {aid for _d, aid, _sc in sin["score_rows"]}
    activos_con = {aid for _d, aid, _sc in con["score_rows"]}
    assert len(activos_sin) == _N_ACTIVOS
    assert activos_con == set(ids[:12])


def test_el_paso_de_fechas_saltea_fechas(db):
    """`date_step` es la perilla que hace pagable un filtro sobre años: mide una
    fecha de cada N en vez de todas."""
    from app.services import backtest_service

    _mundo()
    todas = backtest_service.draft_score_rows(
        [{"signal_key": "sig_a", "weight": 1}], None, {"horizons": [1]},
        date_step=1)
    salteadas = backtest_service.draft_score_rows(
        [{"signal_key": "sig_a", "weight": 1}], None, {"horizons": [1]},
        date_step=5)

    f_todas = {d for d, _a, _s in todas["score_rows"]}
    f_salteadas = {d for d, _a, _s in salteadas["score_rows"]}
    assert len(f_salteadas) == (len(f_todas) + 4) // 5
    assert f_salteadas <= f_todas


def test_la_cobertura_se_informa_por_key(db):
    """Un componente sin dato no excluye al activo: le renormaliza el score y
    lo deja mejor rankeado que a uno completo. La cobertura es lo único que
    permite ver eso, así que tiene que viajar en el resultado."""
    from app.models import signal_store
    from app.services import backtest_service

    ids, fechas = _mundo()
    s = get_session()
    # sig_b sin dato para la mitad de los activos.
    from app.models import SignalDefinition
    sig_b = s.query(SignalDefinition).filter_by(key="sig_b").first()
    rt = signal_store.read_sig_table(s, sig_b.id)
    s.execute(rt.delete().where(rt.c.asset_id.in_(ids[:12])))
    s.commit()

    out = backtest_service.draft_score_rows(
        [{"signal_key": "sig_a", "weight": 1},
         {"signal_key": "sig_b", "weight": 1}], None, {"horizons": [1]})

    assert out["cobertura"]["sig_a"] == 100.0
    assert 40.0 < out["cobertura"]["sig_b"] < 60.0


# ── Holdout ──────────────────────────────────────────────────────────────────

def test_el_holdout_reserva_el_ultimo_cuarto(db):
    """El corte parte la historia disponible de señales, no un calendario
    inventado."""
    _mundo()
    vent = prudencia.ventana(get_session())

    ultimo = _D0 + datetime.timedelta(days=_N_FECHAS - 1)
    esperado = _D0 + datetime.timedelta(
        days=int((ultimo - _D0).days * (1 - prudencia.FRACCION_HOLDOUT)))
    assert vent["corte"] == esperado.isoformat()
    assert vent["date_to"] == esperado.isoformat()
    assert vent["modo"] == "exploracion"


def test_el_corte_no_depende_de_lo_que_pidio_la_llamada(db):
    """Si el holdout fuera 'el último cuarto de lo pedido', mover date_to entre
    intentos iría descubriendo el tramo reservado de a pedazos sin pedirlo
    nunca. El corte tiene que ser el mismo para toda llamada."""
    _mundo()
    s = get_session()
    a = prudencia.ventana(s)
    b = prudencia.ventana(s, date_to="2024-01-20")
    c = prudencia.ventana(s, date_from="2024-01-05", date_to="2024-01-15")

    assert a["corte"] == b["corte"] == c["corte"]


def test_la_exploracion_no_toca_el_tramo_reservado(db):
    """EXCLUIR, no ocultar. Tapar el número del último tramo no serviría de
    nada mientras el IC medio global lo siguiera teniendo adentro."""
    from app.services import backtest_service

    _mundo()
    vent = prudencia.ventana(get_session())
    out = backtest_service.compute_draft_backtest(
        [{"signal_key": "sig_a", "weight": 1}], None,
        {"horizons": [1], "date_from": vent["date_from"],
         "date_to": vent["date_to"]})

    corte = datetime.date.fromisoformat(vent["corte"])
    assert max(p["date"] for p in out["ic_points"]) <= corte


def test_revelar_holdout_devuelve_solo_el_tramo_reservado(db):
    """Y arranca DESPUÉS del corte: si se superpusiera con la exploración, el
    número ya no sería independiente."""
    _mundo()
    vent = prudencia.ventana(get_session(), revelar_holdout=True)

    corte = datetime.date.fromisoformat(vent["corte"])
    assert vent["modo"] == "holdout"
    assert datetime.date.fromisoformat(vent["date_from"]) > corte
    assert datetime.date.fromisoformat(vent["date_to"]) > corte


def test_sin_historia_no_se_inventa_un_holdout(db):
    """Una instalación sin señales calculadas no puede reservar nada, y decirlo
    es mejor que devolver un rango vacío que no mide nada."""
    vent = prudencia.ventana(get_session())
    assert vent["modo"] == "sin_holdout"
    assert vent["corte"] is None


# ── Contador de intentos ─────────────────────────────────────────────────────

def test_el_contador_sube_por_usuario(db):
    caller = AiCaller(user_id=_ANA)
    assert prudencia.registrar_intento(caller) == 1
    assert prudencia.registrar_intento(caller) == 2
    assert prudencia.registrar_intento(AiCaller(user_id=_ADMIN)) == 1


def test_el_aviso_de_sobreajuste_aparece_recien_al_cuarto_intento(db):
    """Antes es exploración normal, y un cartel en cada respuesta es ruido que
    se termina ignorando."""
    assert prudencia.aviso_intentos(1) is None
    assert prudencia.aviso_intentos(3) is None
    assert "4" in (prudencia.aviso_intentos(4) or "")


# ── Las herramientas ─────────────────────────────────────────────────────────

def test_las_dos_herramientas_estan_registradas(db):
    """Sin registro no existen para la IA (la allowlist es el registro)."""
    nombres = {t.name for t in registry.all_tools()}
    assert {"backtest_strategy_draft",
            "simulate_strategy_draft_portfolio"} <= nombres


def test_la_herramienta_corre_sin_ninguna_estrategia(db):
    _mundo()
    out = registry.call("backtest_strategy_draft", AiCaller(user_id=_ANA),
                        {"components": [{"signal_key": "sig_a", "weight": 1}],
                         "horizons": [1]})

    assert out["guardado"] is False
    assert out["modo"] == "exploracion"
    assert out["corte_holdout"]
    assert out["simulaciones_en_esta_sesion"] == 1
    assert out["ic"]


def test_un_filtro_ilegible_falla_en_vez_de_correr_sin_filtro(db):
    """`parse_tree` ante un JSON que no puede leer devuelve None, o sea corre
    SIN filtro y sin avisar. Un borrador medido sobre todo el universo creyendo
    que filtró es un resultado equivocado imposible de detectar leyéndolo."""
    _mundo()
    with pytest.raises(ValueError, match="filtro"):
        registry.call("backtest_strategy_draft", AiCaller(user_id=_ANA),
                      {"components": [{"signal_key": "sig_a", "weight": 1}],
                       "filter_conditions": {"op": "AND", "children": [
                           {"cond": {"left": {"type": "indicator",
                                              "key": "no_existe"},
                                     "operator": ">",
                                     "right": {"type": "const", "value": 1}}}]}})


def test_demasiados_componentes_se_rechazan(db):
    _mundo()
    with pytest.raises(ValueError, match="componentes"):
        registry.call("backtest_strategy_draft", AiCaller(user_id=_ANA),
                      {"components": [{"signal_key": "sig_a", "weight": 1}] * 9})


def test_la_lista_vacia_de_estrategias_sugiere_el_borrador(db):
    """El cartel va donde se choca la pared: una lista vacía leída sin contexto
    se informa como 'no hay nada que analizar', y es falso."""
    out = registry.call("list_strategies", AiCaller(user_id=_ANA), {})
    assert out["total"] == 0
    assert "backtest_strategy_draft" in out["sugerencia"]


# ── Nivel C sin estrategia ───────────────────────────────────────────────────

def test_la_cartera_del_borrador_corre_y_no_escribe(db):
    from app.models import Strategy
    from app.services import backtest_service
    from app.services import portfolio_backtest_service as pbs

    _mundo()
    borrador = backtest_service.draft_score_rows(
        [{"signal_key": "sig_a", "weight": 1}], None, {"horizons": [1]})
    out = pbs.run_draft_portfolio_backtest(borrador["score_rows"], top_n=5)

    assert out["ranking"]["equity"]
    assert out["benchmark_ew"]["equity"]
    Session.remove()
    assert get_session().query(Strategy).count() == 0


def test_la_cartera_del_borrador_no_mira_mas_alla_del_periodo(db):
    """El calendario de la simulación sale de los precios, así que sin techo la
    cartera seguiría operando más allá del último score — sobre el tramo que se
    decidió no mirar."""
    from app.services import backtest_service
    from app.services import portfolio_backtest_service as pbs

    _mundo()
    hasta = (_D0 + datetime.timedelta(days=20)).isoformat()
    borrador = backtest_service.draft_score_rows(
        [{"signal_key": "sig_a", "weight": 1}], None,
        {"horizons": [1], "date_to": hasta})
    out = pbs.run_draft_portfolio_backtest(borrador["score_rows"], top_n=5)

    assert max(out["dates"]) <= datetime.date.fromisoformat(hasta)
