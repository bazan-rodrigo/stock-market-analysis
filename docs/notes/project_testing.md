---
name: suite-de-tests-pytest
description: Existe suite pytest (182 tests de lógica pura); correrla antes de cada push
metadata: 
  node_type: memory
  type: project
  originSessionId: 4589549a-6aad-4d01-a4e5-246338bd5547
---

Desde julio 2026 el proyecto tiene una suite de pytest en `tests/` (182 tests, ~2 s) que cubre la lógica pura: signal_engine, pnf_service, ratios fundamentales, helpers técnicos (fechas, RSI, drawdowns, zonas de régimen/volatilidad, camino rápido del delta, checksum/benchmark staleness, orden de fases rebuild/update), composites anidadas, score de estrategias, soporte/resistencia (sr_service), períodos de retorno (returns_service), normalización RRG (rrg_service) y validación de datos importados (import_service).

Técnica para blindar orquestación DB-touching sin romper la convención "nunca tocar la base": monkeypatch de las funciones pesadas (ver test_indicator_pipeline_order.py) para verificar solo el ORDEN de las llamadas. Útil cuando un bug real fue de secuencia entre dos funciones, no de una fórmula.

**Why:** el flujo del usuario es pushear a master sin correr la app; la suite es la única red de seguridad automatizada.

**How to apply:**
- Correr `venv\Scripts\python.exe -m pytest` ANTES de cada commit que toque servicios — sin que el usuario lo pida.
- El venv local de Windows ya tiene las dependencias instaladas (todas menos mysqlclient y yfinance).
- `tests/conftest.py` apunta `DATABASE_URL` a un stub sqlite antes de importar `app`; `Config.DATABASE_URL` es overrideable por env desde el commit 7a8a641.
- Al agregar lógica de cálculo nueva, agregar tests en el archivo correspondiente; los tests codifican reglas de negocio acordadas (29 de febrero, "el último precio es preliminar", shares más reciente de la ventana TTM). Ver [[decisiones-tecnicas-acordadas]].
