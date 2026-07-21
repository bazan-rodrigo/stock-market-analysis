"""Guardia de purge_assets: un activo usado como componente de un sintético
no se puede borrar (salvo que el sintético caiga en el mismo lote).

Sin la guardia, la FK RESTRICT de synthetic_component rechazaba recién el
DELETE final de assets — cuando purge_assets ya había borrado y commiteado la
historia por lotes: el activo quedaba vivo pero sin señales (bug real). La
guardia corta ANTES de tocar nada, con el mismo estilo de mensaje que el
chequeo de benchmark de delete_asset.
"""
import sys
import types
from datetime import date, timedelta

import pytest

# Esta PC de desarrollo no tiene yfinance (ver CLAUDE.md) y asset_service lo
# arrastra vía app.sources.registry → yahoo.py. Un módulo vacío alcanza para
# importar: ningún test de acá toca la descarga. En el Codespace, donde el
# paquete real existe, setdefault no lo pisa.
sys.modules.setdefault("yfinance", types.ModuleType("yfinance"))


def _seed(comp_id, syn_id, n_precios=3):
    from app.database import Base, engine, get_session
    import app.models  # noqa: F401
    from app.models import (Asset, Price, PriceSource, SyntheticComponent,
                            SyntheticFormula)
    Base.metadata.create_all(engine)
    s = get_session()
    if s.get(PriceSource, 1) is None:
        s.add(PriceSource(id=1, name="test")); s.flush()
    for aid in (comp_id, syn_id):
        if s.get(Asset, aid) is None:
            s.add(Asset(id=aid, ticker=f"SY{aid}", price_source_id=1))
    s.flush()
    f = SyntheticFormula(asset_id=syn_id, formula_type="ratio")
    s.add(f); s.flush()
    s.add(SyntheticComponent(formula_id=f.id, asset_id=comp_id,
                             role="numerator", weight=1.0))
    d0 = date(2024, 1, 1)
    for i in range(n_precios):
        s.add(Price(asset_id=comp_id, date=d0 + timedelta(days=i),
                    close=100 + i, high=101 + i, low=99 + i))
    s.commit()
    return s


def _n_precios(s, asset_id):
    from app.models import Price
    return s.query(Price).filter(Price.asset_id == asset_id).count()


def test_purge_de_un_componente_se_rechaza_sin_tocar_nada():
    from app.models import Asset
    from app.services.asset_service import purge_assets
    s = _seed(7101, 7102)

    with pytest.raises(ValueError, match="SY7101.*SY7102"):
        purge_assets(s, [7101])

    # La guardia corta antes de cualquier DELETE: activo e historia intactos.
    assert s.get(Asset, 7101) is not None
    assert _n_precios(s, 7101) == 3


def test_delete_asset_propaga_el_rechazo():
    from app.services.asset_service import delete_asset
    s = _seed(7111, 7112)
    with pytest.raises(ValueError, match="componente"):
        delete_asset(7111)
    s.rollback()


def test_purge_conjunto_componente_mas_sintetico_pasa():
    from app.models import Asset
    from app.services.asset_service import purge_assets
    s = _seed(7121, 7122)

    assert purge_assets(s, [7121, 7122]) == 2
    assert s.get(Asset, 7121) is None
    assert s.get(Asset, 7122) is None


def test_purge_de_no_componente_no_se_bloquea():
    from app.database import Base, engine, get_session
    import app.models  # noqa: F401
    from app.models import Asset, PriceSource
    from app.services.asset_service import purge_assets
    Base.metadata.create_all(engine)
    s = get_session()
    if s.get(PriceSource, 1) is None:
        s.add(PriceSource(id=1, name="test")); s.flush()
    s.add(Asset(id=7131, ticker="SY7131", price_source_id=1))
    s.commit()

    assert purge_assets(s, [7131]) == 1
    assert s.get(Asset, 7131) is None
