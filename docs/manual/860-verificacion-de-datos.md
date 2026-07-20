---
slug: verificacion-de-datos
title: Verificación de datos
chapter: 8. Administración
order: 860
roles: admin
page: /admin/verify
---

Responde una pregunta que ninguna otra pantalla responde: **¿lo que está
guardado es correcto?** Recalcula los indicadores desde cero y los compara
contra lo que hay almacenado, para detectar diferencias que las actualizaciones
incrementales puedan haber dejado.

La pantalla tiene dos bloques independientes.

## Suite de tests

Corre la batería de pruebas de lógica del sistema: fórmulas, decisiones internas
de cálculo, equivalencias. **No toca la base de datos**, así que es seguro
correrla en cualquier momento.

Sirve para descartar que un problema venga del código antes de salir a buscarlo
en los datos. Si los tests pasan y el resultado igual se ve mal, el problema
está en los datos y el segundo bloque es donde seguir.

## Verificación de datos reales

Recalcula los indicadores o los ratios fundamentales **desde cero y en memoria,
sin escribir nada**, y compara ese resultado contra lo guardado. Además corre
chequeos de coherencia: valores fuera de su rango posible (un RSI que no está
entre 0 y 100), categorías desconocidas, números absurdos.

**Es solo lectura sobre los datos de origen, así que se puede correr contra
producción sin riesgo.**

Una diferencia entre lo recalculado y lo guardado significa que el valor
almacenado quedó mal —típicamente porque una actualización incremental no
alcanzó a corregir algo—, y se arregla con un recálculo completo de ese activo
desde el [Centro de Datos](/manual/centro-de-datos).

## De acá sale el símbolo ⚠️ de los selectores

Cuando corrés la verificación sobre todos los activos, o sobre los ya marcados,
los resultados **quedan registrados**. Ese registro es el que hace aparecer el
símbolo **⚠️** al lado del nombre de un activo en los selectores de
[Análisis de Activo](/manual/analisis-de-activo),
[Rotación Relativa](/manual/rotacion-relativa) y
[Evolución Relativa](/manual/evolucion).

Es decir: **si nunca corriste la verificación, nunca vas a ver esas marcas**, y
la ausencia de marcas no significa que los datos estén bien. Significa que nadie
verificó.

> **El símbolo avisa que ese activo tiene un problema detectado, pero no dice
> cuál.** Para saber qué le pasa hay que volver acá y mirar el detalle de la
> verificación.

## Cuándo conviene correrla

- **Después de una migración o una restauración** de la base.
- **Después de cambiar la definición de un indicador**, para confirmar que el
  recálculo dejó todo consistente.
- **Cuando algo no cierra** en una pantalla de análisis y ya descartaste que sea
  un problema de precios.
- **De forma periódica**, como control de rutina. El sistema puede correr una
  verificación semanal automática — ver [Scheduler de tareas](/manual/scheduler).

> Verificar **todos** los activos recalcula mucho y lleva tiempo. Si ya sabés
> cuál te preocupa, verificá ese solo; y para los controles de rutina, la opción
> de revisar únicamente los que ya están marcados es bastante más rápida.
