---
name: project-render-dash-sin-red
description: "2-ago-2026: ningún test construía componentes Dash — una prop que dbc 2.x rechaza vaciaba el modal de estrategias en producción sin romper la pantalla"
metadata: 
  node_type: memory
  type: project
  originSessionId: f076c123-f0e5-44f4-8a7c-832753c1889b
  modified: 2026-08-02T05:36:13.167Z
---

**El bug (producción, 2-ago-2026):** una estrategia con 4 componentes se abría
en el modal de edición **sin ninguno**, y la previsualización decía
"SCORE = (sin componentes)". La grilla, en cambio, mostraba `Comp. = 4`.

Los datos estaban intactos. `toggle_modal` armaba el store perfecto
(`uids: [0,1,2,3]` con señales y pesos). Lo que fallaba era
`render_comp_rows`: el `dbc.Input` del peso llevaba `title=...`, y
**dash-bootstrap-components 2.0.4 rechaza esa prop con TypeError**. Lo
introdujo f9337ca (peso con signo). Arreglo: el tooltip en un `html.Div`
envolvente.

**El modo de falla es lo que hay que recordar:** el crash ocurre DENTRO de un
callback, así que no rompe la pantalla — se come la salida de ese Output y
todo lo demás (nombre, descripción, filtro) se ve perfecto. Un render que
explota parece un dato que falta. Alcance real: desde f9337ca **no se podía
agregar ningún componente a ninguna estrategia** (ni "+ Nueva", ni
"+ Componente", ni editar), y nadie lo notó porque la pantalla "cargaba bien".

**Por qué ningún trinquete lo vio:** la suite entera (1585 tests) es de lógica
pura y **jamás construye un componente Dash**. Todo lo que se arma dentro de un
callback —filas dinámicas, árboles de filtro, tablas de preview— está fuera de
cualquier red. Es el mismo patrón de [[project-trinquetes-faltantes]]: no era
una lista desactualizada, era una zona sin cobertura.

Cubierto con `tests/test_strategy_modal_rows.py`: llama a `render_comp_rows` y
exige una fila por componente, buscando los controles **por su id
pattern-matching y no por posición** (envolver un control en otro contenedor es
un cambio de layout legítimo y no debe romper el test). Queda pendiente la
misma red para los demás renders dinámicos.

Dato útil para el futuro: en dbc 2.0.4 `Button`, `Textarea` y `Badge` aceptan
`title`; `Input`, `Select`, `Switch` y `Col` **no**. `requirements.txt` pide
`dash-bootstrap-components>=1.5.0` sin tope, así que Railway resuelve 2.x.
