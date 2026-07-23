---
name: project-postgres-only-estudio
description: "Se evaluó retirar el soporte dual y quedarse solo con PostgreSQL — DESCARTADO el 23-jul-2026: el dual SE MANTIENE, el motor es una elección de instalación; sobrevive la cosecha PG, que no exige cortar nada"
metadata:
  node_type: memory
  type: project
  originSessionId: 26b2a194-5f13-4ef4-8a67-87db3554ba16
  modified: 2026-07-23T01:43:55.782Z
---

# DECISIÓN: el soporte dual SE MANTIENE (23-jul-2026)

**No cortar. No borrar ramas de MySQL.** Se estudió a fondo retirar el soporte
dual y la decisión final fue conservarlo.

El criterio del usuario: **el motor de base de datos es una elección de
INSTALACIÓN** (MySQL o PostgreSQL), independiente del entorno donde corra la
app, y las dos opciones se mantienen disponibles. Hoy usa Railway con
PostgreSQL y no tiene motivos para cambiar, pero conserva a propósito la
posibilidad de MySQL y de Codespace "por cualquier cosa que pase en el futuro".
Corolario suyo, que es la crítica al diseño actual: **no está bien que se
instalen los dos motores si solo se va a usar uno** — hoy `DB_ENGINE=both`
instala ambos servicios y `requirements.txt` trae los dos drivers siempre
(Railway compila `mysqlclient`, una extensión en C, para nunca usarlo).

**Por qué se descartó el corte** (el dato que lo mató): el plan afirmaba que la
etapa C dependía de la B. Verificado contra el código, esa dependencia es **una
sola línea** — el `parametrize` de `tests/test_bootstrap_portability.py` que
renderiza contra `mysql://`. Ni la etapa C ni la D (donde está toda la
performance) necesitaban el corte. Sin esa dependencia quedaban ~130 líneas de
código de producción sobre 45.000, a cambio de 1,5-2 sesiones y del riesgo
concentrado en `signal_backfill_range.py:636` (elige la arquitectura de
concurrencia, y la suite es ciega ahí). **Cuarta revisión del veredicto; las
cuatro convergieron en que el corte valía menos cuanto más de cerca se lo
miraba.**

Documentos, ambos con encabezado de "no ejecutar":
`docs/notes/design_postgres_only.md` y `docs/notes/plan_corte_pg_only.md`.

## Lo que SOBREVIVE del estudio

- **Etapa A: HECHA** (`d75d7d2`, `3cbdace`) y se queda, porque eran bugs vivos y
  los arreglos sirven en ambos motores: `lock_timeout` (condicional por
  dialecto), login determinista, unicidad de usuario sin distinguir mayúsculas,
  `set_bulk_load_checks` borrada, `"1146"` fuera del run_lock.
- **Etapa 0: PENDIENTE** en Railway y sigue valiendo — ver [[pendientes-proxima-sesion]].
- **La cosecha PG (ex etapa D)**: COPY, CLUSTER en vez de VACUUM FULL,
  fillfactor, LATERAL, UNLOGGED. **No exige cortar nada**: va detrás del
  despacho que `db_compat` ya tiene. El inventario con call sites reales está
  en la sección 3 de `design_postgres_only.md`. Ojo: el "3-10x de COPY" es un
  número de folleto, no medido acá, y las dos últimas victorias de perf
  vinieron de *escribir menos*, no de escribir más rápido.

## Trabajo propuesto y no empezado

Desenredar el motor del entorno: `DB_ENGINE` como única elección válida en
cualquier entorno, drivers separados por motor (`requirements-mysql.txt` /
`requirements-postgres.txt`), y `both` deja de ser un modo de instalación.
Detalle a resolver antes: Railway autodetecta `requirements.txt`, así que hay
que ver si el archivo a instalar se puede declarar en el repo o si obliga a
tocar el panel.

## Tensión abierta, sin resolver

Mantener MySQL como opción real chocaría con "no instalar los dos": probarla de
verdad exige levantar MySQL al lado. Estado honesto: **la rama MySQL no se
ejercita hace semanas** — todo el refactor de tablas anchas se probó solo contra
PostgreSQL y contra MariaDB nunca corrió. O sea que "soportado" hoy significa
que el código está, no que esté validado; revivirlo costaría una corrida de
verificación.

## Hallazgo grave que salió de revisar la etapa A (preexistente, ya arreglado)

En tablas anchas el worker bufferiza y vuelca una vez por lote; si el volcado
agotaba los reintentos se descartaba el buffer —ninguna fila escrita— pero los
resultados por código igual llegaban al padre, que consolidaba `ind_asset_meta`
con checksums calculados EN MEMORIA. El delta siguiente veía los metadatos
coincidentes, tomaba el camino rápido tail-mode y **el hueco no se rellenaba
nunca**. Lección general: **un resultado calculado en memoria no prueba que se
haya escrito** — si el commit puede fallar después, los metadatos que gobiernan
deltas no pueden salir de él.

## Lecciones de método

- **Verificar las citas contra la fuente antes de construir encima.** La v1 del
  estudio citó el diseño dual cortando la frase: el original decía que las
  ventajas PG "se posponen **o van detrás del mismo despacho**" y quedó solo "se
  posponen". Eso convirtió una disyunción en un dilema y sostuvo todo el
  argumento a favor de cortar.
- **Verificar las dependencias que un plan afirma**, no heredarlas. El "B→C" de
  este plan era una línea.
- La revisión adversarial posterior (8 agentes) encontró la cita truncada, 3
  afirmaciones falsas y ~20 imprecisiones sobre el propio estudio.

Relacionado: [[project-postgresql-migracion]], [[project-scaling-target]],
[[project-ind-wide-tables]], [[feedback-mariadb]], [[entorno-de-verificacion]].
