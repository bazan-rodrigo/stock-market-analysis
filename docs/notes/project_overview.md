---
name: Stock Market Analysis — Visión general
description: App web de análisis técnico de activos financieros para analistas e inversores internos
type: project
originSessionId: d56247d5-0d87-4acc-839e-a171f01f972d
---
Herramienta web interna para seguimiento y análisis de activos financieros.

**Stack fijo (no negociable):**
- Python + Dash (UI) + MySQL + Flask-Login
- Producción: Linux + Apache 2 + mod_wsgi
- Desarrollo: Windows + servidor local Dash

**Usuarios:** admin (acceso total) y analista (solo lectura/visualización).

**Funcionalidades:**
1. Autenticación con roles
2. ABMs de referencia: países, monedas, mercados, tipos de instrumento, sectores, industrias, fuentes de precios
3. Gestión de activos (CRUD + autocompletado desde fuente + importación Excel)
4. Actualización de precios diaria automática (APScheduler)
5. Gráfico técnico con indicadores (SMA, EMA, Bollinger, RSI, MACD, Estocástico, ATR)
6. Screener con filtros y columnas ordenables

**Flujo de trabajo:** Edición en PC local (Windows, sin BD) → git push → git pull en GitHub Codespace donde corre la app con MariaDB.
**Why:** La PC local no tiene base de datos; el Codespace tiene el entorno completo.
**How to apply:** Después de cada cambio, siempre commitear y pushear; recordarle al usuario que haga `git pull` en el Codespace.
