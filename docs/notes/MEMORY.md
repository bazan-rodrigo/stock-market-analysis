# Memoria del proyecto

## Cómo trabajar acá

- [Idioma](feedback_language.md) — responder siempre en español
- [Pedir confirmación antes de editar](feedback_confirmacion_cambios.md) — presentar la solución y esperar el "sí"; una PREGUNTA pide explicación, no implementación
- [Commits con sesiones en paralelo](feedback_commits_sesiones_paralelas.md) — 2-ago: `git commit -- <archivos>` SIEMPRE. `git commit` a secas publica todo lo staged lo haya puesto quien sea; `git add` de lo propio NO alcanza. Pasó dos veces
- [Verificación: SOLO Railway](feedback_entorno_verificacion.md) — el Codespace ya no se usa; verificar = producción. Los `profile_*` que escriben toman el `run_lock`
- [Motor de BD: elección de INSTALACIÓN](feedback_mariadb.md) — PG o MySQL, se elige al instalar; hoy Railway+PG y **el dual se mantiene**
- [Reflejar todo cambio en UI y SPEC](feedback_reflejar_en_ui_y_spec.md) — motor + interfaz + contrato publicado se tocan en el mismo commit
- [Registro de pantallas nuevas](feedback_registro_pantallas.md) — sin auto-discovery: `_PAGES` + `_CALLBACKS` + navbar; `test_module_registration.py` es la red
- [Modal no se cierra ante error](feedback_modal_on_error.md) — solo el callback de save cierra, y solo en éxito
- [Estrategias = packs](feedback_strategy_packs.md) — cuando pide una estrategia, generar el pack en `strategy_packs/`, no pasos manuales
- [Un indicador nuevo se ve en el GRÁFICO](feedback_indicador_se_ve_en_el_grafico.md) — incluye su panel, no es trabajo aparte. **`_SLOTS` NO es la lista de lo que el gráfico dibuja**. Molde: `load_rs52w_overlay`. Ya se perdió dos veces
- [Popup del DatePicker — no tocar](feedback_calendar_popup.md) — fondo blanco sin resolver; el usuario decidió dejarlo

## Dónde no hay red

- [Los renders dentro de callbacks no tienen red](project_render_dash_sin_red.md) — 2-ago: `dbc.Input` rechaza `title` en dbc 2.x y el crash es DENTRO del callback → no rompe la pantalla, **parece un dato que falta**. Una estrategia con 4 componentes se abría vacía. Los tests son lógica pura y **nunca construyen un componente Dash**
- [Trinquetes: 5 de 6 huecos CERRADOS](project_trinquetes_faltantes.md) — 1/2-ago. **El patrón: un trinquete sirve si DERIVA del código y se pudre si codifica una lista a mano.** Hechos el #2, el **#4 (3 bugs vivos: el reset no vaciaba las anchas, por CLI no vaciaba NADA, `run_history` sin clasificar)**, el **#3 (destapó que `purge_assets` dejaba huérfanas las filas de las anchas al borrar un activo)**, el **#5 (la prosa del SPEC, atada en los dos sentidos)** y el **#6, que el relevamiento no había visto: las herramientas de IA no son pantallas, así que el manual describía 8 de 15 y nadie se enteraba**. **Queda abierto solo el #1**: el espejo JS de `simulateTrades`, sin ninguna red
- [Objetivo: 10.000 activos](project_scaling_target.md) — **MÉTODO en 4 pasos** (cProfile=dónde / leer código=qué / medir=cuánto / verificar que no cambie el resultado). Medido: delta 105,63 ms/activo con 4 procs → entra en el timeout. **Tres estimaciones mías previas fueron malas**: las partes aisladas no suman el todo

## IA / MCP

- [IA con cuenta propia — MCP: **ANDANDO EN PRODUCCIÓN**](project_ia_mcp.md) — 1/2-ago, **14 herramientas de solo lectura**. Servicio `mcp` aparte en Railway, migraciones 0099 (token en `users`) + 0100 (OAuth: el conector remoto NO acepta token pegado a mano). Riesgo central resuelto: **el gate de visibilidad no se hereda** (vive en la UI) y se re-aplica en `app/ai`. Ninguna IA escribe señales; backtest y carteras corren **sin persistir**, con KPIs por tramo contra el sobreajuste. Destapó 2 bugs de producción ajenos a la IA. **2-ago: Gemini no conectaba — que ande con Claude no prueba nada sobre otro cliente.** Los clientes de DCR ahora se registran como PÚBLICOS; un fallo de OAuth no dejaba NINGÚN rastro en el log y hubo que interrogar producción a mano
- [Packs como estándar publicado](project_packs_estandar.md) — SPEC.md v1 + catálogo por instalación + validador offline; el import resuelve atributos por NOMBRE. **El SPEC se desfasó y el trinquete no lo vio: ataba las LISTAS, no la PROSA**

## Arquitectura y datos

- [Señales/estrategias en tablas anchas — CUTOVER HECHO](project_sig_wide_tables.md) — **las `sig_{id}`/`strat_res_{id}` YA NO EXISTEN** (0094). Hoy `signal_values_wide` + `strategy_results_wide`, se leen por `read_sig_table()`/`read_strat_table()`. Medido 3,7× en señales. **Consecuencia viva: crear/borrar una definición es ALTER TABLE sobre una tabla COMPARTIDA**, ya no CREATE/DROP TABLE
- [Tablas anchas de indicadores](project_ind_wide_tables.md) — fases 1-5, wide por default, ~5,5× menos footprint (0077/0078/0079)
- [Reducción de footprint](project_reduccion_footprint.md) — ronda 1 cerrada y medida: 2,5 → 2,3 GB. float4 en `sig_*` NO rinde (padding MAXALIGN de PG)
- [Soporte dual: SE MANTIENE](project_postgres_only_estudio.md) — **no borrar ramas de MySQL**; el corte a PG-only se evaluó y se DESCARTÓ. Sobrevive la cosecha PG (COPY/CLUSTER/LATERAL), que no exige cortar nada
- [Migración a PostgreSQL](project_postgresql_migracion.md) — fases 1-4 hechas: `db_compat`, bootstrap create_all/stamp, entorno `DB_ENGINE`
- [ProcessPool con partición por activos](project_processpool_particion_activos.md) — resuelve GIL + caché a 10k activos; ya implementado
- [Corridas en el proceso web](project_corridas_proceso_web.md) — gunicorn `--timeout 1800` (120 mataba las corridas sin dejar error). Railway: 8 vCPU / 8 GB. Migrar a `worker.py` DIFERIDO: el timeout es un parche que vuelve a apretar a 10k

## Módulos

- [Módulo de backtesting](project_backtest.md) — niveles A-D (señal/reglas/cartera/comparar+walk-forward) + Carteras reales y teóricas; 0070/0080/0083/0084
- [Promover cartera hereda la config gated](project_hallazgo_promover_cartera.md) — congela la corrida gated como `PortfolioRun` y la vincula (0095). **PENDIENTE: verificar el flujo vivo**
- [Manual de usuario web](project_manual_usuario.md) — 59 secciones en `docs/manual/`, filtradas por rol; los tests atan el manual al código. **El modo invitado se ELIMINÓ**: login siempre obligatorio
- [Sistema de diseño único de UI](project_sistema_diseno_ui.md) — `ui_constants` como sistema global + `test_ui_consistency.py`. **`custom.css` y `dark_theme.js` = ZONA INTOCABLE**
- [Grillas a 10.000 activos — todo en ag-grid](project_grillas_10k.md) — 20 grillas migradas, cero `dash_table.DataTable`. Ojo ag-grid 35: hace falta `theme: "legacy"`. **CERRADO: borrar/editar validado en Railway el 3-ago**
- [Resiliencia/monitoreo de corridas](project_resiliencia_corridas.md) — bug del rebuild interrumpido arreglado + `run_history` persistida (0096). DIFERIDO: build-and-swap y el chequeo de cobertura
- [Reinicio TOTAL a fábrica](project_reset_fabrica.md) — botón + `--reset` que dejan la base como recién instalada. **VERIFICADO en Railway**
- [Carga masiva de activos](project_carga_masiva_alto_volumen.md) — import Excel en 2 fases + redescarga global por el camino batch compartido

## Indicadores y señales

- [Indicadores 0098: posición 52W, ADX, volumen relativo](project_indicadores_0098.md) — **el hallazgo no fue un indicador**: el score de estrategia RENORMALIZA ante dato faltante mientras el filtro EXCLUYE, así que al activo sin dato le va sistemáticamente mejor. Criterio de admisión: escalar **comparable entre activos**. **PENDIENTE Railway: upgrade 0098 + recálculo completo**
- [Indicadores con historia: Drawdown % y ATR % (0097)](project_indicadores_con_historia.md) — faltaban por tres motivos distintos. **VERIFICADO**. **Hilo CERRADO**: las 3 continuaciones están DESCARTADAS, no re-proponerlas
- [Filtro de estrategias](project_filtro_estrategias.md) — árbol AND/OR + editor de señales + backfill delta; semántica as-of; indicadores por plantilla diferido
- [Removidas las señales de grupo](project_remover_grupo.md) — 0090 dropea `group_signal_value`; el import RECHAZA `source=group`/`scope`. `group_scores` y el Mapa sobreviven
- [Mapa de Tendencia: scores al vuelo](project_score_semanal_mensual_mapa.md) — calcula desde `ind_trend_*` con selector de fecha, ya no persiste `group_scores` (0092 dropea la tabla)
- [Scores en días sin precio propio — SIN DECIDIR](project_scores_dias_sin_precio.md) — as-of arrastra scores a fechas no cotizadas; 2 alternativas guardadas, retomar

## Base

- [Proyecto: Stock Market Analysis](project_overview.md) — app web Dash+Flask de análisis técnico, con admin y analistas
- [Decisiones técnicas acordadas](project_decisions.md) — APScheduler en proceso único, Alembic, screener pre-calculado, Yahoo Finance only
- [Suite de tests](project_testing.md) — ~1585 tests de **lógica pura**, nunca tocan la base real; correr `pytest` antes de cada push
- [Pendientes próxima sesión](project_pendientes.md) — log sesión por sesión. Vivos: aplicar migraciones en Railway, usuarios duplicados sin distinguir caso, y **los tokens de GitHub en texto plano en los remotes**
- [AVISO: sesiones en paralelo se pisan los commits](project_cleanup_commiteado_por_error.md) — pasó dos veces (f626f01, 49c8229). NO reescribir historia (decidido). Ver [[feedback-commits-sesiones-paralelas]]
- **SUPERADAS** (se conservan por historia, no son estado actual): [group_scores por grupo consumido](project_group_scores_scope.md) — las señales de grupo se removieron; [tabla por señal/estrategia](project_tablas_por_senal.md) — reemplazada por las tablas anchas
