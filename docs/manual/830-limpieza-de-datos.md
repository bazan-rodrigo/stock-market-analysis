---
slug: limpieza-de-datos
title: Limpieza de datos
chapter: 8. Administración
order: 830
roles: admin
page: /admin/cleanup
---

Tiene tres partes que hacen cosas muy distintas, y conviene no confundirlas:
una **mide** el espacio, otra lo **recupera sin borrar nada**, y la tercera
**borra datos de forma irreversible**.

## Uso de espacio en disco

Solo informa: muestra el tamaño total de la base, un desglose por familia
(indicadores, señales, precios…) y las tablas más grandes. **Actualizar**
recalcula la medición.

Sirve para responder "¿qué está creciendo?" antes de decidir qué hacer. Lo
habitual es que el grueso del espacio se lo lleven los indicadores, las señales
y los precios, que son las tablas con una fila por activo y por día.

## Recuperar espacio

**No borra datos.** Compacta las tablas del sistema y devuelve al disco el
espacio que dejan los recálculos.

Cada vez que se recalcula un indicador o una señal, la versión anterior de los
datos queda ocupando lugar aunque ya no se use. Con el tiempo, una tabla puede
ocupar varias veces lo que realmente necesita. Esta operación limpia eso, y es
la respuesta correcta cuando el disco crece sin que hayan aumentado los datos.

> **Corré esto en un momento tranquilo.** Mientras compacta, bloquea cada tabla
> que va procesando, y quien esté consultando pantallas puede quedar esperando.
> Si hay una actualización del pipeline en curso —o la corrida automática
> nocturna—, el botón directamente no arranca: la pantalla avisa que hay otra
> operación pesada en curso y hay que esperar a que termine.

Es una operación segura de repetir: en el peor caso no recupera nada.

## Borrado de datos operativos

> **Es irreversible y no pide más confirmación que el diálogo que aparece.**
> Leé esta sección entera antes de apretar el botón.

Borra todo lo que el sistema **calcula** —indicadores, señales, resultados de
estrategias, ratios fundamentales—, las corridas guardadas de backtest y de
cartera, y además los eventos de mercado, los aliases del catálogo y los
registros de corridas, que no se calculan pero se pueden volver a descargar o
importar. La pantalla lista en detalle qué se borra y qué se conserva —esa
lista es la fuente autorizada, mirala antes de ejecutar.

No toca los datos que se bajaron de la fuente: ni las cotizaciones ni los
balances trimestrales de las empresas. Esos son la materia prima con la que se
vuelve a calcular todo lo demás.

La distinción que importa es entre lo que se puede regenerar y lo que no:

| | ¿Se recupera? |
|---|---|
| Indicadores, señales, estrategias, ratios fundamentales | **Sí.** Se regeneran con los botones de recálculo completo del [Centro de Datos](/manual/centro-de-datos), aunque tarda. |
| Corridas guardadas de backtest y de cartera | **No.** Hay que volver a correrlas, y una corrida vieja no se puede reproducir exactamente si cambiaron los datos. |

Esa segunda fila es la que suele doler. Si tenés corridas guardadas que te
importan, **anotá su configuración antes de limpiar**.

### Cuándo tiene sentido

Es una operación de mantenimiento excepcional, no de rutina. Los dos casos
razonables:

1. **Quedó basura de una migración o de definiciones viejas** y querés
   regenerar todo desde cero con las definiciones actuales.
2. **Estás preparando un entorno de prueba** a partir de una copia de
   producción y no necesitás lo derivado.

Si tu problema es solo espacio en disco, **probá primero Recuperar espacio**:
resuelve la mayoría de los casos sin borrar nada.

### Después de limpiar

El sistema queda con los activos, los precios, los balances trimestrales, las
definiciones, las carteras con su registro de operaciones y los usuarios, pero
sin nada calculado: las
pantallas de análisis van a aparecer vacías hasta que regeneres.
El orden de reconstrucción está en el
[Centro de Datos](/manual/centro-de-datos). Contá con que un recálculo completo
sobre muchos activos lleva un buen rato.
