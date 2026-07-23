---
name: project-postgres-only-estudio
description: "Se evaluó retirar el soporte dual y quedarse solo con PostgreSQL — DESCARTADO el 23-jul-2026: el dual SE MANTIENE, el motor es una elección de instalación; sobrevive la cosecha PG, que no exige cortar nada"
metadata:
  node_type: memory
  type: project
  originSessionId: 26b2a194-5f13-4ef4-8a67-87db3554ba16
  modified: 2026-07-23T14:30:17.867Z
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

## Desenredo del motor y el entorno — HECHO (23-jul, `29fbb5f` + `e43e281`)

El problema real no era el dual sino que **había dos mecanismos que no se
hablaban**: `DB_ENGINE` (solo lo leían los scripts de setup, decidía qué
servicio se instalaba) y `DATABASE_URL` (decidía contra qué corría la app). Sin
URL, `config.py` armaba una de MySQL hardcodeada ignorando `DB_ENGINE`: se podía
instalar PostgreSQL y arrancar contra MySQL. `setup.sh` ya lo venía compensando
con un parche (exportar `DATABASE_URL` en `~/.bashrc`).

Ahora `DB_ENGINE` es el eje y **la app lo lee**. Reglas de resolución en
`_resolve_db` (`app/config.py`, testeada):
- las dos definidas y contradiciéndose → **RuntimeError al importar la config**;
- solo la URL → el motor se **deduce** de ella (no rompe Railway, que nunca
  definió `db_engine`);
- solo el motor → la URL se deriva; ninguna → default `postgres`.
- **sqlite queda fuera del chequeo** a propósito: es el stub de la suite.

Drivers separados (`requirements-postgres.txt` / `requirements-mysql.txt`):
`requirements.txt` traía los dos y Railway compilaba `mysqlclient` para nunca
usarlo. En Railway el driver lo agrega **`railpack.json`** (el builder es
**Railpack**, no Nixpacks) extendiendo el paso de install con la sintaxis
`"..."`. Dos precauciones deliberadas: el comando instala `requirements.txt`
además del driver (si el `"..."` no se aplicara, alcanza igual), y el fallback
`${DB_ENGINE:-postgres}` hace que ande aunque la variable no esté.

`devcontainer.json` ya no fija el motor ni `DB_PORT`/`DB_USER`/`DB_PASSWORD`
(le ganaban a lo derivado por ser variables de entorno). La elección la persiste
`setup.sh` en **`conf.properties`** (gitignoreado = config de esa instalación).
El modo `both` se retiró de los dos scripts.

**VERIFICADO en el deploy del 23-jul** (`c1272c7`, tras un build fallido):

- **Railpack corre los comandos por un shell** (`sh -c` en el mensaje de error):
  `${DB_ENGINE:-postgres}` **sí se expande**. Era lo único del diseño que había
  quedado sin confirmar.
- **La sintaxis `"..."` de extensión funciona**, en `commands` y en `inputs`.
- **Lo que faltaba (y es la trampa a recordar): el paso de install NO ve todo
  el repo.** Railpack le copia solo `requirements.txt` para cachear esa capa,
  así que un comando que lea otro archivo falla con `Could not open requirements
  file`. Hay que declararlo como entrada local del paso:
  `"inputs": ["...", {"local": true, "include": [...]}]`.
- **Un build fallido no despliega**: la versión anterior siguió corriendo todo
  el episodio. Esa propiedad es la razón por la que se eligió arriesgar en el
  build y no en runtime, y funcionó como se esperaba.

Detalle completo en `guide_deploy.md` §3.1b.

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
