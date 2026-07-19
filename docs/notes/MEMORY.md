# Memoria del proyecto

- [Guía de deploy — Codespace y Railway](guide_deploy.md) — Cómo levantar cada entorno + casos: traer el head, armar staging manual, conectar a otra base, apagar sin perder datos, recrear la base, auto-deploy
- [Módulo de backtesting](project_backtest.md) — MVP deciles+IC hecho (14-jul, migración 0070); gate de lectura contra scores as-of; fases 2/3 pendientes
- [Rediseño Backtest + Carteras](design_backtest_carteras_rediseno.md) — 18-jul: 2 módulos (Backtest niveles A-D + Carteras biblioteca de N reales/teóricas), motor y vistas compartidos; plan en 6 fases (migraciones 0078+); Fase 0 (motor de métricas puro) en progreso

- [Proyecto: Stock Market Analysis](project_overview.md) — App web Dash+Flask para análisis técnico de activos financieros, con admin y analistas
- [Decisiones técnicas acordadas](project_decisions.md) — APScheduler proceso único, Alembic, screener pre-calculado (nomenclatura current/history/scores), Yahoo Finance only, admin hardcoded
- [Suite de tests pytest](project_testing.md) — 182 tests de lógica pura en tests/; correr `pytest` antes de cada push (el venv local ya tiene las deps)
- [Pendientes próxima sesión](project_pendientes.md) — GIL confirmado como cuello de botella del pool (ThreadPoolExecutor→ProcessPoolExecutor pendiente); varios bugs de datos/threading arreglados jul-2026; indicadores nuevos elegidos
- [Objetivo: soportar 10000 activos](project_scaling_target.md) — Hoy 500 de prueba; priorizar perf de indicadores full_sample con el patrón de profiling aislado
- [Filtro de estrategias + roadmap indicadores](project_filtro_estrategias.md) — Filtro AND/OR + editor de señales + backfill delta, todo en vivo (12-jul); semántica as-of de indicadores; próximo natural: backtest por deciles; indicadores por plantilla diferido
- [group_scores solo para grupos consumidos](project_group_scores_scope.md) — 13-jul (f5b396f): group_scores/group_signal_value se calculan solo para los grupos que una estrategia usa (derivado del filtro); pendiente verificar en Codespace
- [Scores en días sin precio propio — SIN DECIDIR](project_scores_dias_sin_precio.md) — as-of arrastra scores a fechas no cotizadas; 2 alternativas guardadas (gate vs flag preliminar) en docs/notes/design_scores_dias_sin_precio.md, retomar
- [Servicio de base de datos es MariaDB](feedback_mariadb.md) — En el Codespace usar `sudo service mariadb start`, no mysql
- [Modal no se cierra si hay error al guardar](feedback_modal_on_error.md) — El modal ABM debe permanecer abierto en error; solo el callback de save cierra el modal (en éxito)
- [Registro de pantallas nuevas](feedback_registro_pantallas.md) — Sin auto-discovery: _PAGES + _CALLBACKS en app/__init__.py + navbar; test_module_registration.py es la red
- [Idioma de comunicación](feedback_language.md) — Responder siempre en español
- [Pedir confirmación antes de aplicar cambios](feedback_confirmacion_cambios.md) — Presentar la solución y esperar "sí" antes de editar archivos
- [Estrategias como archivos de import](feedback_strategy_packs.md) — Cuando pide una estrategia, generar los xlsx en strategy_packs/, no pasos manuales
- [Popup calendario DatePicker — no tocar](feedback_calendar_popup.md) — Fondo blanco del popup no resuelto tras múltiples intentos; usuario decidió dejarlo
- [Migración futura a PostgreSQL](project_postgresql_migracion.md) — Plan a futuro sin fecha; ver puntos MySQL-específicos a migrar (ON DUPLICATE KEY UPDATE, driver)
- [ProcessPool con partición por activos](project_processpool_particion_activos.md) — Diseño elegido para escalar el pool de indicadores (resuelve GIL + caché a 10k activos); se encara junto con PostgreSQL
- [Tablas anchas de indicadores por cadencia](design_ind_wide_tables.md) — Reduce footprint (~5× lo diario) agrupando ind_{code} en ind_daily/weekly/monthly, lossless y compute-positivo; Fase 1 en progreso (jul-2026, mapping+migración 0077); riesgo: as-of con columnas NULL
