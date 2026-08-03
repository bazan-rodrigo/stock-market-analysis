"""La herramienta `indicator_distribution` como adaptador.

La cuenta la hace el servicio (y la prueba `test_indicator_stats.py`); acá se
verifica lo que es responsabilidad de la capa de IA: que esté registrada, que
delegue tal cual, y que la respuesta lleve el aviso de cobertura — sin él, un
modelo lee un percentil y calibra una señal sin enterarse de que el indicador
cubre a la mitad de la base.
"""
import pytest

from app.ai import registry
from app.ai.caller import AiCaller


@pytest.fixture()
def fake_service(monkeypatch):
    from app.services import indicator_stats_service

    llamadas = []

    def _fake(code, fecha=None, escala=None):
        llamadas.append({"code": code, "fecha": fecha, "escala": escala})
        return {"code": code, "type": "num", "n": 3,
                "percentiles": {"p50": 1.5}}

    monkeypatch.setattr(indicator_stats_service, "distribucion_indicador", _fake)
    return llamadas


def test_esta_registrada_y_delega_los_argumentos(fake_service):
    out = registry.call("indicator_distribution", AiCaller(user_id=7),
                        {"code": "atr_pct_daily", "fecha": "2026-07-31",
                         "escala": {"min": 6, "max": 1}})
    assert fake_service == [{"code": "atr_pct_daily", "fecha": "2026-07-31",
                             "escala": {"min": 6, "max": 1}}]
    assert out["percentiles"]["p50"] == 1.5


def test_la_respuesta_avisa_de_la_cobertura(fake_service):
    """El dato faltante no castiga: se saltea y renormaliza los pesos, así que
    al activo sin dato le va MEJOR. Es contraintuitivo y ya mordió una vez, por
    eso viaja en cada respuesta en vez de estar solo en el manual."""
    out = registry.call("indicator_distribution", AiCaller(user_id=7),
                        {"code": "rvol_daily"})
    assert "renormalizan" in out["como_leerlo"]
    assert "filtro de elegibilidad" in out["como_leerlo"]


def test_el_esquema_exige_el_codigo_y_no_admite_nada_mas():
    esquema = registry.get("indicator_distribution").input_schema
    assert esquema["required"] == ["code"]
    assert esquema["additionalProperties"] is False
    assert set(esquema["properties"]) == {"code", "fecha", "escala"}
