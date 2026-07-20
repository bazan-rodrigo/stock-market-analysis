---
slug: activos-sinteticos
title: Activos sintéticos
chapter: 5. Activos
order: 520
roles: admin
page: /admin/synthetic
---

Acá se define **cómo se calcula** el precio de los activos calculados: ratios,
índices propios, canastas. Qué es un sintético, los cuatro tipos de fórmula y
sus limitaciones (no tienen volumen, y solo cotizan en las fechas en que
cotizaron **todos** sus componentes) está en
[Activos, sintéticos y grupos](/manual/activos-y-grupos); acá va el
procedimiento.

> **Antes de venir acá**: el activo destino tiene que existir. Crealo en
> [Gestión de activos](/manual/gestion-de-activos) con la fuente de precios
> **Calculado**. Si no tiene esa fuente, no aparece en el selector de destino.

## El listado

Una fila por fórmula, con **Ticker**, **Nombre**, **Tipo** y **Fórmula** —esta
última escrita, del estilo `CCL = (GGAL.BA) / (GGAL)`: es la forma más rápida de
auditar de un vistazo qué calcula cada uno. Los botones de la segunda fila
operan sobre lo seleccionado:

| Botón | Requiere | Qué hace |
|---|---|---|
| **Editar** | Exactamente 1 | Abre la fórmula para modificarla. |
| **Calcular Delta** | 1 o más | Calcula solo los precios nuevos. Rápido; mantiene el historial. |
| **Calcular Completo** | 1 o más | Borra y recalcula **todos** los precios desde el inicio. |
| **Eliminar** | 1 o más | Borra la fórmula. |

## Crear o editar una fórmula

**+ Nuevo** abre el editor. Al elegir el **Tipo de fórmula** aparece una tarjeta
de ayuda con la expresión matemática y el significado de cada parámetro para ese
tipo — leela, resuelve casi todas las dudas.

| Campo | Cuándo aplica | Notas |
|---|---|---|
| **Tipo de fórmula** | Siempre | Ratio, Promedio ponderado, Suma ponderada o Índice base. |
| **Activo destino** | Siempre | Solo lista activos con fuente **Calculado**. |
| **Valor base** | Solo Índice base | Cuánto vale el índice en la fecha de partida. Por defecto 100. |
| **Fecha base** | Solo Índice base | Obligatoria. Si el componente no cotizó ese día exacto se usa el precio anterior más cercano. |

Debajo se cargan los **Componentes**, uno por fila: el **Activo** (cualquiera
del sistema, incluido otro sintético), el **Rol** —que **solo aparece en
Ratio**: Numerador o Denominador— y el **Peso**, que por defecto es 1 y que en
Promedio ponderado e Índice base no necesita sumar 100, porque la fórmula
normaliza sola. La **×** quita la fila y **+ Agregar componente** suma otra.

El recuadro gris de abajo muestra la **fórmula armándose en vivo** mientras
cargás: usalo como control antes de guardar.

### Validaciones al guardar

El editor no cierra si algo falta, y te dice qué:

- Falta el tipo de fórmula o el activo destino.
- No cargaste ningún componente, o alguno quedó sin activo elegido.
- Es de tipo Índice base y no pusiste fecha base.
- **El activo destino ya tiene una fórmula.** No se permiten dos: seleccionala
  en la tabla y usá **Editar**.

> **Guardar la fórmula no calcula precios.** Es solo la definición. Después de
> guardar —y siempre que cambies una fórmula existente— seleccioná el sintético
> y corré **Calcular Completo**: si no, los precios que quedan son los de la
> definición anterior.

## Calcular precios

**Calcular Delta** agrega solo lo que falta y rehace la última fecha (el último
precio siempre es preliminar). Es lo del día a día.

**Calcular Completo** borra la serie y la reconstruye entera, y además rehace la
historia de indicadores del sintético. Es lo que corresponde cuando cambiaste la
fórmula, cambiaste los componentes, o los precios de un componente se
corrigieron hacia atrás.

Una barra muestra el avance `hechos / total` y los dos botones de cálculo
—**Calcular Delta** y **Calcular Completo**— quedan deshabilitados mientras
corre. Al terminar informa cuántos precios se
insertaron y detalla los que fallaron, si hubo alguno.

> **Calcular Completo sobre muchos sintéticos a la vez puede tardar bastante.**
> Reconstruye toda la serie de cada uno más su historia de indicadores.

## Eliminar

**Eliminar** borra la **fórmula**, no el activo: el activo destino sigue
existiendo, con la fuente Calculado y con los precios que ya se le habían
calculado, pero sin nada que lo actualice. Si lo que querés es hacer desaparecer
el sintético por completo, borrá el activo desde
[Gestión de activos](/manual/gestion-de-activos).

## Exportar e importar fórmulas

**Exportar fórmulas** baja un Excel con **todas** las fórmulas, una fila por
componente, e **Importar fórmulas** lee ese mismo formato: es la vía para
versionar definiciones, replicarlas o cargar muchas de una.

| Columna | Obligatoria | Qué espera |
|---|---|---|
| `synthetic_ticker` | **Sí** | Ticker del activo destino. Debe existir y tener fuente **Calculado**. Agrupa las filas: todas las de un mismo ticker forman una fórmula. |
| `formula_type` | **Sí** | Uno de: `ratio`, `weighted_avg`, `weighted_sum`, `index`. Se toma de la primera fila del grupo. |
| `component_ticker` | **Sí** | Ticker del componente. Debe existir como activo. |
| `role` | **Sí** | `numerator` o `denominator` para los ratios; `component` para el resto. |
| `weight` | **Sí** | Numérico. Si no se puede interpretar, se asume 1. |
| `base_value` | No | Solo para `index`. Vacío: queda sin valor base. |
| `base_date` | No | Solo para `index`, formato `AAAA-MM-DD`. |

Reglas de la importación:

- Si el activo destino **ya tiene** una fórmula, se **reemplaza** entera.
- Si el activo destino no existe, no tiene fuente Calculado, el tipo de fórmula
  no es uno de los cuatro válidos, o **alguno** de los componentes no existe, se
  rechaza **toda esa fórmula** — pero las demás del archivo se importan igual.
- El resultado aparece en una tabla debajo de los botones, con el detalle por
  ticker.

> Igual que al guardar a mano, **importar no calcula precios**. Seleccioná los
> sintéticos importados y corré **Calcular Completo**.

## Y después

Un sintético es un activo más: entra a los agregados de sus grupos y compite en
el ranking. Incorporarlo a la historia de señales y estrategias exige un
**recálculo completo** — ver
[Cómo se calcula todo](/manual/conceptos-pipeline). Para generar conversiones de
moneda **de a cientos** no uses esta pantalla: está
[Activos en Divisa](/manual/activos-en-divisa).
