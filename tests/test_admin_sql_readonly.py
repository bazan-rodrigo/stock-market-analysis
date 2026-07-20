"""_is_read_only clasifica una sentencia como lectura (la consola SQL admin la
ejecuta y hace commit inmediato, sin red de commit/rollback) o como escritura
(pendiente de commit/rollback explicito).

El riesgo asimetrico: un falso NEGATIVO (DML tratado como lectura) se
auto-commitea sin vuelta atras y ademas el export lo re-ejecuta -> datos
perdidos. Un falso POSITIVO (lectura tratada como escritura) solo obliga a un
commit/rollback de mas. Por eso ante la duda debe devolver False.
"""
from app.callbacks.admin_sql_callbacks import _is_read_only


def test_lecturas_puras_son_read_only():
    for s in ("SELECT * FROM assets",
              "  select 1",
              "EXPLAIN SELECT * FROM prices",
              "SHOW TABLES",
              "DESC assets",
              "DESCRIBE assets",
              "WITH x AS (SELECT id FROM assets) SELECT * FROM x"):
        assert _is_read_only(s) is True, s


def test_dml_directo_no_es_read_only():
    for s in ("DELETE FROM prices WHERE asset_id = 1",
              "UPDATE assets SET ticker = 'X'",
              "INSERT INTO assets (ticker) VALUES ('X')",
              "TRUNCATE TABLE ind_daily",
              "DROP TABLE foo"):
        assert _is_read_only(s) is False, s


def test_cte_data_modifying_no_es_read_only():
    """El bug: WITH que envuelve DML. En PostgreSQL ejecuta el DELETE, y la
    consola lo clasificaba como lectura -> commit inmediato + re-ejecucion en
    export."""
    for s in ("WITH borradas AS (DELETE FROM prices WHERE asset_id = 1 "
              "RETURNING *) SELECT count(*) FROM borradas",
              "with x as (update assets set ticker='Y' returning id) "
              "select * from x",
              "WITH n AS (INSERT INTO assets(ticker) VALUES('Z') RETURNING id) "
              "SELECT * FROM n"):
        assert _is_read_only(s) is False, s


def test_explain_analyze_de_dml_no_es_read_only():
    """EXPLAIN ANALYZE DELETE ejecuta el DELETE en PostgreSQL."""
    assert _is_read_only("EXPLAIN ANALYZE DELETE FROM prices") is False
    assert _is_read_only("EXPLAIN UPDATE assets SET ticker='X'") is False
    # EXPLAIN de un SELECT sigue siendo lectura
    assert _is_read_only("EXPLAIN ANALYZE SELECT * FROM assets") is True


def test_falso_positivo_es_tolerable():
    """Un SELECT que menciona una keyword de escritura en un string/nombre cae
    del lado seguro (se trata como escritura). No es lo ideal para el usuario,
    pero nunca pierde datos."""
    # se prefiere seguro: devuelve False aunque sea en realidad una lectura
    assert _is_read_only(
        "WITH x AS (SELECT id FROM audit WHERE accion = 'DELETE') "
        "SELECT * FROM x") is False
