# Stock Market Analysis

Aplicacion web para el analisis tecnico y fundamental de acciones.  
Desarrollada en **Python**, usando **Dash**, **SQLAlchemy**, **MySQL** y la API de **Yahoo Finance**.  
Puede ejecutarse sobre **Apache + mod_wsgi** o directamente con el servidor Dash local.

---

## 🚀 Descripcion general

**Stock Market Analysis** permite a analistas y administradores:

- Importar activos manualmente o de forma masiva desde archivos CSV.
- Descargar y almacenar precios historicos de multiples fuentes.
- Ejecutar actualizaciones diarias de precios (por scheduler o manual).
- Consultar los errores de actualizacion y reintentar individualmente.
- Visualizar graficos, screeners e indicadores en la interfaz Dash.

Arquitectura en **capas separadas**:

1. **Persistencia:** MySQL + SQLAlchemy ORM.  
2. **Logica de negocio:** CRUD, indicadores, ETL, actualizacion de precios.  
3. **Presentacion:** Dash + Plotly, con pestañas (tabs) y diseño responsivo.  
4. **Integracion:** Servidor Apache con mod_wsgi o entorno local.

---

## 🧩 Funcionalidades

- ✅ Descarga diaria de precios OHLCV desde **Yahoo Finance** con `yfinance`.  
- ✅ Arquitectura modular y extensible para agregar nuevas fuentes.  
- ✅ Importacion masiva de activos y asociacion automatica a la fuente.  
- ✅ Actualizacion diaria tolerante a fallos (no detiene el proceso).  
- ✅ Logging completo con **Loguru** (pantalla + archivos rotativos).  
- ✅ Tabla `historical_prices` particionada por año.  
- ✅ Usuarios con roles `admin` y `analyst`.  
- ✅ Sesiones persistentes con Flask-Login.

---