# Stock Market Analysis — Especificación funcional

## Instrucciones iniciales

Leé esta especificación completa antes de hacer cualquier cosa.

Luego respondé con:
- Cómo entendiste el producto y para qué sirve.
- Qué arquitectura técnica proponés y por qué.
- Qué decisiones tomaste y cuáles querés consultarme antes de arrancar.

No generes ningún archivo hasta que yo confirme el plan.

---

## Qué es esta aplicación

Una herramienta web para analistas e inversores que quieren seguir y analizar activos del mercado financiero. Permite gestionar un listado de activos, visualizar su evolución histórica con indicadores técnicos, filtrar y ordenar activos según criterios de análisis, y mantener los precios actualizados automáticamente todos los días.

La aplicación tiene dos tipos de usuario: **administradores** y **analistas**. No es pública: solo acceden usuarios registrados por el administrador.

---

## Contexto técnico

Esto no es negociable porque ya está definido por el entorno de deploy:

- **Lenguaje**: Python
- **Interfaz web**: Dash
- **Base de datos**: MySQL
- **Autenticación**: Flask-Login
- **Deploy producción**: Linux, Apache 2 + mod_wsgi
- **Desarrollo**: Windows, servidor local de Dash

Para todo lo demás (estructura de carpetas, ORM, librerías, patrones de diseño), proponé vos lo que consideres mejor y justificalo.

---

## Configuración

La app lee su configuración en este orden de prioridad:

1. Variables de entorno del sistema operativo.
2. Archivo `conf.properties` en la raíz del proyecto (usado cuando no hay variables de entorno disponibles, por ejemplo en Windows durante el desarrollo).

Esto permite que en producción Linux se usen variables de entorno del sistema, y en desarrollo Windows se use el archivo de propiedades sin configuración adicional. El archivo `conf.properties` nunca se commitea al repositorio.

---

## Funcionalidades

### 1. Autenticación

- Los usuarios inician sesión con usuario y contraseña.
- Las contraseñas se almacenan encriptadas en la base de datos. Nunca se guarda la contraseña en texto plano.
- Nadie puede registrarse solo: el administrador crea las cuentas.
- Si un usuario no está autenticado y trata de acceder a cualquier pantalla, lo redirige al login.
- Hay dos roles: **admin** (acceso total) y **analista** (solo lectura y visualización).
- Al instalar la app por primera vez, se crea automáticamente un usuario admin inicial.

---

### 2. Tablas de referencia (ABM)

La app tiene tablas de referencia que el administrador puede gestionar. Cada una tiene su propia pantalla de alta, baja y modificación.

**Entidades:**

- **Países**: nombre, código ISO.
- **Monedas**: nombre, código ISO (ej: USD, ARS, EUR).
- **Mercados / bolsas**: nombre, país al que pertenece.
- **Tipos de instrumento**: nombre (acción, ETF, cripto, índice, bono, commodity, moneda, etc.), moneda de cotización por defecto (elegida del ABM de monedas). La lista debe ser extensible sin modificar código.
- **Sectores**: nombre.
- **Industrias**: nombre, sector al que pertenece.
- **Fuentes de precios**: nombre, descripción, activa/inactiva.

**Reglas de borrado para todas las entidades:**
- El borrado es físico.
- Antes de borrar cualquier registro, la app valida en código que no esté referenciado por ninguna otra entidad y lo refuerza con foreign keys en la base de datos. Si está referenciado, el borrado se rechaza con un mensaje claro indicando qué lo está usando.

---

### 3. Gestión de activos

El administrador puede mantener el listado de activos financieros que la app monitorea.

**Datos de un activo:**
- Ticker
- Nombre
- País de la bolsa donde cotiza
- Mercado / bolsa
- Tipo de instrumento
- Moneda de cotización
- Sector (opcional)
- Industria (opcional)
- Fuente de precios (la default es Yahoo Finance)
- Activo / inactivo

**Operaciones disponibles:**
- Agregar un activo manualmente.
- Editar los datos de un activo existente.
- Activar o desactivar un activo. Los inactivos no se actualizan automáticamente ni aparecen en el screener.
- Eliminar un activo. El borrado es físico e incluye toda su historia de precios. Se valida en código y por foreign key antes de ejecutar.

**Autocompletado desde la fuente de precios:**
Al ingresar un ticker, el usuario puede presionar un botón para consultar la fuente de precios seleccionada. La app intentará validar que el ticker existe y completar en pantalla los campos disponibles según lo que ofrezca la fuente (nombre, sector, industria, etc.). El usuario puede editar los campos completados antes de guardar. Esta funcionalidad no es exclusiva de Yahoo Finance: cada fuente implementa lo que pueda ofrecer.

**Importación masiva desde Excel:**
La importación tiene su propia pantalla dedicada con las siguientes funcionalidades:

- Botón para descargar un template Excel vacío con todas las columnas aceptadas y sus nombres exactos, listo para completar.
- Campos obligatorios por fila: ticker y fuente de precios.
- Campos opcionales: todos los demás datos del activo.
- Al importar, cada ticker se valida contra su fuente y se autocompletan los campos disponibles.
- Si un ticker ya existe en la app, se omite y se reporta.
- Lo que no se pueda importar se reporta con el motivo.
- El usuario ve un resumen al finalizar: importados, omitidos por duplicado, fallidos con detalle.
- Los resultados se muestran en una grilla con una fila por ticker procesado, indicando su estado (importado, omitido, error) y el detalle correspondiente.
- El resultado de cada importación se persiste (un registro por activo, se sobreescribe si se vuelve a intentar importar el mismo ticker). La grilla muestra siempre el último resultado conocido para cada ticker. Hay un botón para borrar todos los registros de la grilla.

---

### 4. Actualización de precios

**Actualización automática:**
- Todos los días a un horario configurable, la app descarga los precios de todos los activos activos usando la fuente asignada a cada uno.
- El proceso es tolerante a fallos: si un activo falla, el resto sigue procesándose.

**Lógica de descarga:**
- Si un activo no tiene ningún precio registrado, se descargan todos los precios históricos disponibles en la fuente.
- Si ya tiene precios, se borra el último día disponible y se descarga desde ese día inclusive hacia adelante. Esto garantiza que si el precio fue descargado antes del cierre de mercado, se actualice con el valor final.

**Pantalla de actualización de precios:**
La actualización tiene su propia pantalla dedicada con las siguientes funcionalidades:

- Grilla con una fila por activo activo, mostrando el estado del último intento de actualización: fecha, resultado (éxito o error) y detalle del error si lo hubo.
- El resultado se persiste (un registro por activo, se sobreescribe en cada intento). La grilla siempre refleja el último estado conocido de cada activo.
- Botón para borrar todos los registros de la grilla.
- Botones de acción: actualizar un activo individual, reintentar un activo que falló, lanzar actualización completa de todos los activos activos, borrar la historia de precios de un activo y redescargar desde cero.

---

### 5. Gráfico técnico

El analista puede visualizar la evolución de precio de cualquier activo con indicadores técnicos superpuestos.

- Seleccionar el activo desde un buscador.
- Elegir el rango de fechas a visualizar.
- Elegir el tipo de visualización del precio: velas japonesas (candlestick) o línea.
- El volumen siempre se muestra en un panel debajo del precio.
- Desde un panel lateral el analista puede activar o desactivar indicadores y ajustar sus parámetros.
- Indicadores sobre el precio: SMA, EMA, Bandas de Bollinger.
- Indicadores en paneles separados debajo del gráfico: RSI, MACD, Estocástico, ATR.
- El sistema de indicadores debe ser fácilmente extensible: agregar un nuevo indicador en el futuro no debe requerir modificar la lógica de la interfaz.

---

### 6. Screener

Herramienta para explorar y comparar activos según su comportamiento técnico.

**Filtros disponibles:**
- País de la bolsa (multi-select)
- Mercado / bolsa (multi-select)
- Tipo de instrumento (multi-select)
- Sector (multi-select)
- Industria (multi-select)
- Rango de RSI (slider min/max)
- Posición del precio respecto a SMA 20, SMA 50 y SMA 200 (por encima / por debajo, seleccionables independientemente)

**Tabla de resultados:**
Todas las columnas son ordenables de forma ascendente y descendente, lo que permite por ejemplo encontrar los activos que más bajaron en las últimas 52 semanas simplemente ordenando esa columna.

| Columna | Descripción |
|---|---|
| Ticker | |
| Nombre | |
| Var. diaria | Variación porcentual del día |
| Var. mes | Desde inicio del mes en curso |
| Var. quarter | Desde inicio del quarter en curso |
| Var. año | Desde inicio del año en curso |
| Var. 52s | Últimas 52 semanas |
| RSI | |
| vs SMA20 | Distancia porcentual al SMA 20 |
| vs SMA50 | Distancia porcentual al SMA 50 |
| vs SMA200 | Distancia porcentual al SMA 200 |

Al hacer click en un activo de la tabla, se abre su gráfico técnico.

---

## Fuentes de precios — regla de acceso

Las APIs de las fuentes de precios se consultan **únicamente** en dos situaciones:
1. Durante el proceso de actualización de precios.
2. Durante el autocompletado y validación de tickers.

En ningún otro caso. El gráfico técnico, el screener y el cálculo de indicadores trabajan exclusivamente con los datos almacenados en la base de datos.

---

## Calidad y comportamiento esperado

- La app debe funcionar correctamente tanto en Windows (desarrollo) como en Linux (producción). Usar siempre rutas compatibles con ambos sistemas operativos.
- Todos los errores deben quedar registrados en un log con suficiente detalle para diagnosticar problemas.
- El código debe estar organizado en capas claramente separadas: la interfaz no accede directamente a la base de datos.
- Al instalar la app desde cero, debe haber un script que inicialice la base de datos, cargue los datos de referencia básicos y cree el usuario admin inicial.
