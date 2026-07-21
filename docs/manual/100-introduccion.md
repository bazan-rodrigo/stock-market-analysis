---
slug: introduccion
title: Qué es esta aplicación
chapter: 1. Introducción
order: 100
roles: invitado
---

Esta es una aplicación de **análisis técnico y fundamental de activos
financieros**. Su propósito no es mostrar gráficos de a uno, sino **rankear
cientos o miles de activos todos los días** según criterios que vos definís, y
darte las herramientas para verificar si esos criterios sirvieron.

## Las tres cosas que hace

**1. Guarda y mantiene los datos.** Precios diarios, datos fundamentales
(balances, ratios), eventos de mercado. Los precios y los fundamentales se
actualizan solos todos los días mediante un scheduler interno; los eventos los
carga o importa un administrador.

**2. Calcula un ranking diario.** Sobre esos precios se calculan *indicadores*
(medias móviles, RSI, drawdown, régimen de tendencia…), sobre los indicadores
se calculan *señales* (que traducen un indicador a un puntaje de −100 a +100), y
las señales se combinan en *estrategias* que ordenan todos los activos de mejor
a peor. Este encadenamiento es el corazón del sistema y está explicado en
[Cómo se calcula todo](/manual/conceptos-pipeline).

**3. Te deja comprobar si funcionó.** El módulo de backtest recorre la historia
y mide si los activos que la estrategia puso arriba efectivamente rindieron más
que los que puso abajo. Sin esto, una estrategia es solo una opinión.

## Perfiles de usuario

La aplicación tiene tres perfiles, y lo que ves cambia según cuál te toque —
incluido este manual, que oculta las secciones que no aplican a tu perfil.

| Perfil | Puede |
|---|---|
| **Invitado** | Entra sin usuario propio cuando el acceso público está habilitado. Ve y opera todas las pantallas, igual que un administrador; lo que crea queda sin dueño y después solo un administrador puede editarlo. |
| **Analista** | Las pantallas de análisis y el visualizador de precios, más crear y editar sus propias señales, estrategias y carteras (y ver las públicas). |
| **Administrador** | Todo. Además: alta de activos, actualización manual de datos, tablas de referencia, usuarios, scheduler y herramientas de mantenimiento. |

Si una sección del manual está marcada con la etiqueta **admin**, describe
funcionalidad que solo ve un administrador.

## Cómo está organizada la pantalla

Arriba está la barra de navegación, agrupada por tipo de tarea:

- **Análisis** — las pantallas de consulta: gráficos, comparaciones, screener,
  backtest. Es donde se trabaja el día a día.
- **Activos** *(admin)* — qué activos existen en el sistema y cómo se dan de alta.
- **Datos de Mercado** — el visualizador de precios; para administradores,
  además, las pantallas de actualización de precios y fundamentales, los
  eventos y el Centro de Datos.
- **Configuración** — señales, estrategias y carteras: las definiciones que
  alimentan el ranking. Los administradores ven además los indicadores, las
  fuentes de datos y los parámetros de cálculo.
- **Administración** *(admin)* — usuarios, tareas programadas y mantenimiento.
- **Manual** — este manual.
- **Acerca de** — la presentación pública del sistema (se puede ver incluso
  sin iniciar sesión).

## Cómo usar este manual

El índice de la izquierda agrupa las secciones por capítulo, y el buscador de
arriba busca en el texto completo de todas las secciones que tenés permitido
ver.

Además, **cada pantalla de la aplicación tiene un ícono «?»** — junto al título
o, en las pantallas sin título propio, al extremo derecho de la barra de
controles — que abre directamente la sección que la explica. Si estás perdido en una
pantalla concreta, ese es el camino más corto.

> **Si es tu primera vez**, leé en orden las secciones del capítulo 2. Son
> los conceptos que el resto del manual da por sabidos, y sin ellos varias
> pantallas parecen arbitrarias.
