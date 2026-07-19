"""Reporte de uso de espacio en disco (pantalla Limpieza de datos).

Cubre las piezas PURAS del desglose por familia y el formateo, más que
`database_size_report` no rompe contra el stub sqlite (sin tamaño por tabla).
"""
from app.services import maintenance_service as ms


def test_format_bytes_ordenes_de_magnitud():
    assert ms.format_bytes(0) == "0 B"
    assert ms.format_bytes(512) == "512 B"
    assert ms.format_bytes(1024) == "1.0 KB"
    assert ms.format_bytes(181 * 1024 * 1024) == "181.0 MB"
    assert ms.format_bytes(4.1 * 1024**3) == "4.1 GB"
    assert ms.format_bytes(None) == "0 B"


def test_classify_table_familias():
    assert ms.classify_table("prices") == "Precios"
    assert ms.classify_table("ind_dist_sma50") == "Indicadores"
    assert ms.classify_table("ind_daily") == "Indicadores"
    assert ms.classify_table("current_indicator_values") == "Indicadores"
    assert ms.classify_table("sig_3") == "Señales"
    assert ms.classify_table("group_signal_value") == "Señales"
    assert ms.classify_table("strat_res_2") == "Estrategias"
    assert ms.classify_table("strategy_result") == "Estrategias"
    assert ms.classify_table("group_scores") == "Scores de grupo"
    assert ms.classify_table("fundamental_quarterly") == "Fundamentales"
    assert ms.classify_table("backtest_run") == "Backtest / Carteras"
    assert ms.classify_table("portfolio_transaction") == "Backtest / Carteras"
    assert ms.classify_table("users") == "Otras"


def test_group_by_family_suma_y_ordena():
    tables = [
        ("prices", 100),
        ("ind_a", 30),
        ("ind_b", 20),
        ("sig_1", 5),
        ("users", 1),
    ]
    fam = ms.group_by_family(tables)
    # Ordenado por bytes desc
    assert [r["family"] for r in fam] == [
        "Precios", "Indicadores", "Señales", "Otras"]
    indic = next(r for r in fam if r["family"] == "Indicadores")
    assert indic["count"] == 2
    assert indic["bytes"] == 50


def test_database_size_report_sqlite_no_rompe():
    # sqlite (stub de tests): sin tamaño por tabla, pero la estructura vale.
    rep = ms.database_size_report()
    assert set(rep) == {"total_bytes", "by_family", "tables", "dialect"}
    assert isinstance(rep["by_family"], list)
    assert isinstance(rep["tables"], list)
