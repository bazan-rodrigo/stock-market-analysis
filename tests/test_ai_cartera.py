"""Carteras desde la IA: ver las que hay y simular una hipotética sin crearla.

Una cartera curada es barata de crear —filas planas, sin DDL ni backfill— pero
probar diez combinaciones de pesos igual dejaría nueve carteras que después hay
que borrar a mano. Por eso la IA simula a partir de una lista y no crea nada.

El riesgo de sobreajuste acá es mayor que en el backtest de señales: optimizar
pesos contra una curva histórica es literalmente ajustar parámetros a datos
pasados. De ahí los KPIs por tramo.
"""
import datetime

import pytest
import sqlalchemy as sa

from app.ai import registry
from app.ai.caller import AiCaller
from app.database import Base, Session, engine, get_session

_ADMIN, _ANA, _OTRO = 1, 7, 9


@pytest.fixture()
def db():
    import app.models  # noqa: F401

    Session.remove()
    Base.metadata.create_all(engine)
    tablas = ("portfolio_member", "portfolio_transaction", "portfolio",
              "prices", "assets")
    with engine.begin() as conn:
        for t in tablas:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    yield
    Session.remove()
    with engine.begin() as conn:
        for t in tablas:
            conn.execute(sa.text(f"DELETE FROM {t}"))
    Session.remove()


def _activo(ticker, pendiente, n=60):
    """Un activo con precios que crecen a `pendiente` por rueda."""
    from app.models import Asset, Price

    s = get_session()
    a = Asset(ticker=ticker, name=ticker, price_source_id=1)
    s.add(a)
    s.commit()
    for i in range(n):
        s.add(Price(asset_id=a.id, date=datetime.date(2024, 1, 1) +
                    datetime.timedelta(days=i), close=100.0 + i * pendiente))
    s.commit()
    return a.id


def _cartera(nombre="C", owner=None, publica=True, miembros=None):
    from app.models import Portfolio
    from app.services.portfolio_service import set_members

    s = get_session()
    # composition_method="curated" no es decorativo: resolve_membership
    # devuelve [] si no está, y la cartera se leería como vacía.
    p = Portfolio(name=nombre, ptype="seg", owner_id=owner, is_public=publica,
                  composition_method="curated")
    s.add(p)
    s.commit()
    if miembros:
        # `weights` va por POSICIÓN, no por asset_id
        set_members(s, p.id, [aid for aid, _w in miembros],
                    [w for _aid, w in miembros])
        s.commit()
    return p.id


# ── Visibilidad ───────────────────────────────────────────────────────────────

def test_el_analista_ve_las_publicas_y_las_propias(db):
    _cartera("publica", owner=_ADMIN, publica=True)
    _cartera("propia", owner=_ANA, publica=False)
    _cartera("de otro", owner=_OTRO, publica=False)

    out = registry.call("list_portfolios", AiCaller(user_id=_ANA))
    assert {p["name"] for p in out["portfolios"]} == {"publica", "propia"}


def test_no_se_lee_por_id_una_cartera_ajena(db):
    pid = _cartera("de otro", owner=_OTRO, publica=False)
    with pytest.raises(ValueError):
        registry.call("get_portfolio_performance", AiCaller(user_id=_ANA),
                      {"portfolio_id": pid})


def test_el_mensaje_no_delata_que_la_cartera_existe(db):
    """Si dijera "no tenés permiso" para una y "no existe" para otra, el error
    sería un oráculo para enumerar ids."""
    pid = _cartera("de otro", owner=_OTRO, publica=False)
    ana = AiCaller(user_id=_ANA)

    with pytest.raises(ValueError) as ajena:
        registry.call("get_portfolio_performance", ana, {"portfolio_id": pid})
    with pytest.raises(ValueError) as inexistente:
        registry.call("get_portfolio_performance", ana,
                      {"portfolio_id": 999_999})

    def _sin_id(m):
        return m.replace(str(pid), "X").replace("999999", "X")

    assert _sin_id(str(ajena.value)) == _sin_id(str(inexistente.value))


# ── Simular sin crear ─────────────────────────────────────────────────────────

def test_simular_no_crea_ninguna_cartera(db):
    """LO CENTRAL: probar combinaciones no deja nada que después haya que
    borrar a mano."""
    from app.models import Portfolio, PortfolioMember

    _activo("AAA", 1.0)
    _activo("BBB", 0.5)
    antes = (get_session().query(Portfolio).count(),
             get_session().query(PortfolioMember).count())

    out = registry.call("simulate_portfolio", AiCaller(user_id=_ANA),
                        {"holdings": [{"ticker": "AAA", "weight": 2},
                                      {"ticker": "BBB", "weight": 1}]})
    Session.remove()

    assert (get_session().query(Portfolio).count(),
            get_session().query(PortfolioMember).count()) == antes
    assert out["guardado"] is False
    assert out["kpis"]["total_return"] is not None


def test_los_pesos_se_normalizan_solos(db):
    """No hace falta que sumen 1: 2 y 1 es lo mismo que 0,667 y 0,333."""
    _activo("AAA", 1.0)
    _activo("BBB", 0.5)

    a = registry.call("simulate_portfolio", AiCaller(user_id=_ANA),
                      {"holdings": [{"ticker": "AAA", "weight": 2},
                                    {"ticker": "BBB", "weight": 1}]})
    b = registry.call("simulate_portfolio", AiCaller(user_id=_ANA),
                      {"holdings": [{"ticker": "AAA", "weight": 200},
                                    {"ticker": "BBB", "weight": 100}]})

    assert a["kpis"]["total_return"] == pytest.approx(b["kpis"]["total_return"])
    assert a["composicion"][0]["weight_normalizado"] == pytest.approx(2 / 3)


def test_sin_pesos_es_equiponderada(db):
    _activo("AAA", 1.0)
    _activo("BBB", 0.5)

    out = registry.call("simulate_portfolio", AiCaller(user_id=_ANA),
                        {"holdings": [{"ticker": "AAA"}, {"ticker": "BBB"}]})

    assert all(h["weight_normalizado"] == pytest.approx(0.5)
               for h in out["composicion"])


def test_pesar_mas_al_que_sube_mas_rinde_mas(db):
    """Comprobación de cordura del motor: si no se cumpliera, los pesos no
    estarían llegando a la simulación."""
    _activo("SUBE", 2.0)
    _activo("PLANO", 0.0)
    ana = AiCaller(user_id=_ANA)

    mucho = registry.call("simulate_portfolio", ana,
                          {"holdings": [{"ticker": "SUBE", "weight": 9},
                                        {"ticker": "PLANO", "weight": 1}]})
    poco = registry.call("simulate_portfolio", ana,
                         {"holdings": [{"ticker": "SUBE", "weight": 1},
                                       {"ticker": "PLANO", "weight": 9}]})

    assert mucho["kpis"]["total_return"] > poco["kpis"]["total_return"]


def test_el_ticker_no_distingue_mayusculas(db):
    _activo("AAA", 1.0)
    out = registry.call("simulate_portfolio", AiCaller(user_id=_ANA),
                        {"holdings": [{"ticker": "aaa"}]})
    assert out["composicion"][0]["ticker"] == "AAA"


def test_un_ticker_inexistente_avisa_cual(db):
    """Con el nombre adentro, para que el modelo se corrija en vez de
    reintentar lo mismo."""
    _activo("AAA", 1.0)
    with pytest.raises(ValueError, match="ZZZ"):
        registry.call("simulate_portfolio", AiCaller(user_id=_ANA),
                      {"holdings": [{"ticker": "AAA"}, {"ticker": "ZZZ"}]})


@pytest.mark.parametrize("peso", [0, -1])
def test_un_peso_no_positivo_se_rechaza(db, peso):
    _activo("AAA", 1.0)
    with pytest.raises(ValueError, match="mayor que 0"):
        registry.call("simulate_portfolio", AiCaller(user_id=_ANA),
                      {"holdings": [{"ticker": "AAA", "weight": peso}]})


def test_sin_posiciones_avisa(db):
    with pytest.raises(ValueError, match="al menos una posición"):
        registry.call("simulate_portfolio", AiCaller(user_id=_ANA),
                      {"holdings": []})


def test_activos_sin_precios_avisan(db):
    from app.models import Asset

    s = get_session()
    s.add(Asset(ticker="VACIO", name="V", price_source_id=1))
    s.commit()

    with pytest.raises(ValueError, match="precios"):
        registry.call("simulate_portfolio", AiCaller(user_id=_ANA),
                      {"holdings": [{"ticker": "VACIO"}]})


# ── Tramos: la defensa contra optimizar pesos sobre la historia ───────────────

def test_devuelve_los_kpis_por_tramo(db):
    _activo("AAA", 1.0)
    out = registry.call("simulate_portfolio", AiCaller(user_id=_ANA),
                        {"holdings": [{"ticker": "AAA"}]})

    tramos = out["kpis_por_tramo"]
    assert tramos and len(tramos) == 4
    assert all("desde" in t and "total_return" in t for t in tramos)


def test_los_tramos_cubren_el_periodo_en_orden(db):
    _activo("AAA", 1.0)
    out = registry.call("simulate_portfolio", AiCaller(user_id=_ANA),
                        {"holdings": [{"ticker": "AAA"}]})

    tramos = out["kpis_por_tramo"]
    assert tramos[0]["desde"] == out["desde"]
    assert tramos[-1]["hasta"] == out["hasta"]
    assert [t["desde"] for t in tramos] == sorted(t["desde"] for t in tramos)


def test_cada_tramo_se_mide_por_si_mismo(db):
    """Se reescala a 1 al inicio de cada tramo: si arrastrara el nivel
    acumulado, el retorno de cada tramo incluiría el de los anteriores y todos
    parecerían crecientes."""
    _activo("AAA", 1.0)
    out = registry.call("simulate_portfolio", AiCaller(user_id=_ANA),
                        {"holdings": [{"ticker": "AAA"}]})

    retornos = [t["total_return"] for t in out["kpis_por_tramo"]]
    # Precio lineal ⇒ el retorno porcentual DECRECE tramo a tramo (la base
    # crece). Si se arrastrara el acumulado, seria creciente.
    assert retornos == sorted(retornos, reverse=True)


def test_con_pocas_ruedas_no_inventa_tramos(db):
    _activo("CORTO", 1.0, n=5)
    out = registry.call("simulate_portfolio", AiCaller(user_id=_ANA),
                        {"holdings": [{"ticker": "CORTO"}]})
    assert out["kpis_por_tramo"] is None


def test_la_advertencia_de_sobreajuste_viaja_en_la_respuesta(db):
    """Quien interpreta el número es el modelo, en el momento de leerlo."""
    _activo("AAA", 1.0)
    out = registry.call("simulate_portfolio", AiCaller(user_id=_ANA),
                        {"holdings": [{"ticker": "AAA"}]})

    assert "tramo" in out["como_leerlo"]
    assert "NO se guardó" in out["nota"]


# ── Leer una cartera existente ────────────────────────────────────────────────

def test_devuelve_composicion_y_kpis_de_una_cartera(db):
    a1 = _activo("AAA", 1.0)
    a2 = _activo("BBB", 0.5)
    pid = _cartera("mia", owner=_ANA, publica=False,
                   miembros=[(a1, 0.6), (a2, 0.4)])

    out = registry.call("get_portfolio_performance", AiCaller(user_id=_ANA),
                        {"portfolio_id": pid})

    assert {c["ticker"] for c in out["composicion"]} == {"AAA", "BBB"}
    assert out["kpis"]["total_return"] is not None
    assert out["kpis_por_tramo"]


def test_una_cartera_sin_miembros_avisa_en_vez_de_romper(db):
    pid = _cartera("vacia", owner=_ANA, publica=False)
    out = registry.call("get_portfolio_performance", AiCaller(user_id=_ANA),
                        {"portfolio_id": pid})

    assert out["kpis"] is None
    assert "miembros" in out["aviso"]
