---
slug: conexion-ia
title: Conexión IA
chapter: 7. Configuración
order: 790
roles: analista
page: /ia
# familias_ia lo lee tests/test_contract_coverage.py: tiene que coincidir con
# las familias que declaran las herramientas registradas (app/ai/registry.py).
# Si se estrena una capacidad, va descrita en "Qué puede hacer la IA" y sumada
# acá; si no, falla la suite. No se muestra al lector.
familias_ia: catalogo, indicadores, ranking, backtest, carteras, manual, packs
---


Podés conectar tu propia cuenta de inteligencia artificial —Claude, ChatGPT o
cualquier otra que sepa conectarse a herramientas externas— para preguntarle en
lenguaje natural sobre los datos de la plataforma: qué estrategias hay, cómo
está rankeando una hoy, cómo viene evolucionando un activo, qué significa cada
cálculo.

La idea es que la inteligencia de análisis siga estando acá. La IA no calcula
nada por su cuenta ni inventa fórmulas: le pide los números al sistema, los
mismos que ves vos en pantalla, y te ayuda a leerlos.

## Tu cuenta de IA es tuya

Esto es lo más importante y conviene decirlo de entrada: **la plataforma no ve
ni guarda tu cuenta de inteligencia artificial**. No te pedimos la clave, no la
almacenamos y no pagamos tus consultas. Vos usás tu cuenta desde tu propio
programa de IA, y ese programa se conecta acá para pedir datos.

Lo único que se guarda en esta pantalla es un **token**: un texto largo que le
dice al sistema que quien está preguntando sos vos. Cumple el mismo papel que
tu usuario y contraseña, y se guarda igual de protegido —cifrado en un sentido
que no se puede revertir—, así que ni un administrador puede leerlo.

Hace falta porque sin saber quién pregunta, el sistema no podría mostrarte tus
cosas privadas ni ocultarte las de los demás.

## Generar el token

| Botón | Qué hace |
|---|---|
| **Generar token** | Crea uno nuevo y te lo muestra **una sola vez**. |
| **Revocar** | Lo anula. Cualquier programa que lo estuviera usando deja de tener acceso al instante. |

> **Copialo apenas lo veas.** El token aparece una única vez, al generarlo.
> Después no se puede volver a mostrar, porque el sistema no lo guarda: guarda
> solo una huella que sirve para reconocerlo, no para reconstruirlo. Si lo
> perdés no pasa nada grave — generás otro, y el anterior queda anulado
> automáticamente.

Tratalo como una contraseña: no lo pegues en un chat, en un correo ni en un
documento compartido. Si sospechás que alguien más lo tiene, **revocá y generá
uno nuevo**; es instantáneo y no rompe nada más.

Tenés un token a la vez. Generar uno nuevo reemplaza al anterior, que es
también la forma de rotarlo cada tanto si querés.

## Conectar tu programa de IA

Es un trámite de una sola vez por programa. Tené a mano **el token** que
generaste recién y la **dirección del servicio**, que está en esta misma
pantalla, en el recuadro *Dirección para tu programa de IA*.

Esa dirección **no es la misma con la que entrás a la aplicación**: es una
aparte, dedicada a las consultas de IA, y **termina en `/mcp`**. Si en tu
pantalla aparece un aviso en lugar de la dirección, pedísela al administrador.

1. **Buscá en tu programa de IA dónde se agregan conexiones externas.** Cada uno
   lo llama distinto: *conector*, *extensión*, *servidor MCP* o *aplicación
   personalizada*. Suele estar en la configuración, en la sección de
   integraciones o de herramientas.
2. **Pegá la dirección tal cual, sin agregarle nada.** Ni antes ni después.
3. **Autorizá.** Apenas la agregues, tu programa va a abrir una página de esta
   plataforma pidiéndote permiso. **Ahí va el token, no tu usuario y
   contraseña**: esta conexión nunca te pide la contraseña, y por eso el
   programa de IA nunca llega a verla.
4. **Probá que quedó.** Preguntale algo simple, como *"¿qué estrategias tengo
   disponibles?"*. Si te contesta con tu catálogo, ya está.

Después no hay que hacer nada más: el programa se reconecta solo cada vez que lo
abrís, hasta que revoques el token.

### Si no conecta

El mensaje que muestra tu programa casi nunca dice cuál es el problema de
verdad: habla de que no pudo conectarse, o de que tenés que vincular la cuenta.
Revisá en este orden.

**La dirección.** Es el error más común, lejos. Copiala de esta pantalla en vez
de escribirla: tiene que ser la del servicio de IA —no la de la aplicación web—
y terminar en `/mcp`. Un error clásico es pegar una dirección más larga, sacada
de un mensaje de error: si tiene algo después de `/mcp`, sobra.

**Si ya falló una vez, borrá la conexión y agregala de nuevo** en lugar de
corregirle la dirección. Los programas se guardan cómo salió el primer intento,
y editarlo no siempre repite el proceso desde cero.

**Si la página de autorización te rechaza el token**, generá uno nuevo acá y
volvé a intentar. Puede haber quedado cortado al copiarlo, o anulado porque
generaste otro después.

Si con eso no alcanza, avisale al administrador: del lado del servidor queda
registrado el motivo exacto del rechazo, que es bastante más preciso que lo que
te muestra tu programa.

## Qué puede hacer la IA con tu token

Puede **leer** exactamente lo que vos podrías ver entrando a la aplicación:

- El catálogo de indicadores, señales y estrategias que tenés a la vista —
  incluido **con qué criterio puntúa** cada señal, no solo cómo se llama.
- El ranking de una estrategia en una fecha, y cómo evolucionó el puntaje de un
  activo.
- **Cómo se reparte un indicador entre todos los activos**: percentiles, mínimo,
  máximo y cuántos activos tienen el dato. Es lo que hace falta para discutir si
  los cortes de una señal están bien puestos — si el rango de una señal cae
  fuera de donde vive la masa de los datos, todos los activos terminan con el
  mismo puntaje y esa señal deja de ordenar el ranking, sin que nada dé error.
  Podés pedirle que evalúe una escala tentativa y te diga qué porcentaje de
  activos quedaría recortado.
- El manual, para explicarte cómo funciona cada cálculo de este sistema en
  particular.

También puede **calcular**, sin guardar nada:

- **Backtestear una estrategia** contra la historia y contarte cómo le fue, sin
  que la corrida quede registrada. Incluso puede probar una **variante** —otros
  pesos, otros componentes— sin crear ninguna estrategia nueva: se evalúa sobre
  la misma elegibilidad que la original, así que la diferencia aísla el efecto
  del cambio. Y puede leerte los resultados de las corridas que sí guardaste
  desde la pantalla.
- **Diseñar una estrategia desde cero y medirla**, aunque no exista todavía. Le
  pedís por ejemplo "armame una de momentum que evite las muy volátiles" y la
  arma, la puntúa contra la historia real y te dice si ordena bien los activos —
  todo sin crear nada. Es la diferencia entre que te proponga una idea de
  memoria y que te la proponga con números atrás. **Si tu instalación todavía no
  tiene ninguna estrategia creada, este es el camino**: no hace falta armar una a
  mano primero para poder medirla.
- **Simular la cartera de esa estrategia**: comprar los mejores del ranking,
  rebalancear cada tantas ruedas y descontar costos, para ver cuánto habría
  rendido de verdad y si le gana a comprar todo el mercado sin elegir nada.
  Ordenar bien los activos y ganar plata después de comisiones no son lo mismo.
- **Simular una cartera hipotética** a partir de una lista de activos y pesos,
  sin crearla, y ver el rendimiento de las que ya tenés.

En todos los casos te va a mostrar los números **por tramos de tiempo** además
del promedio. No es un adorno: una estrategia que anduvo bárbaro en un tramo y
mal en los otros no es una buena estrategia, es una casualidad bien contada, y el
promedio sola la tapa. Probar diez variantes y quedarse con la mejor es la forma
más fácil de engañarse — ver [Backtest](/manual/backtest).

### Por qué la IA no ve toda la historia

Hay una parte de esto que conviene que sepas, porque si no los números pueden
sorprenderte: **cuando la IA simula algo, el último tramo de la historia queda
afuera del resultado**. No es un error ni le falta información — está reservado a
propósito.

El motivo es el problema más viejo de esta disciplina. Si probás cincuenta
combinaciones contra los mismos años y te quedás con la que mejor dio, no
encontraste la mejor estrategia: encontraste la que mejor se acomodó a lo que
pasó en esos años en particular. Con suficientes intentos siempre aparece una que
parece excelente por pura casualidad, y la casualidad no se repite cuando ponés
plata.

Por eso el sistema parte la historia: la IA explora y compara en la parte de
adelante, y el tramo final queda guardado sin tocar. Cuando ya se decidió por una
configuración, recién ahí puede pedir ver ese tramo reservado, **una sola vez**.
Si el resultado ahí se parece al que venía viendo, la idea es creíble. Si se
derrumba, era casualidad — y te enteraste antes de operar, que es exactamente
para lo que sirve.

Vale la pena pedirle que te muestre ese número aparte, y también **cuántas
combinaciones probó antes de llegar a la que te propone**. El sistema se lo
recuerda solo, y es un dato tan importante como el rendimiento: veinte intentos y
un resultado espectacular dicen menos que dos intentos y uno modesto.

Y puede **entregarte una estrategia armada**, en vez de dictártela paso a paso:

- Conoce **el formato de intercambio** —el mismo documento que se descarga desde
  la pantalla de [Packs](/manual/packs-de-senales-y-estrategias)—, así que te da
  el archivo listo para subir, con la estrategia y todas las señales que usa.
  Antes lo tenías que conseguir vos y pegárselo en el chat.
- Si sos administrador, además puede **ensayarlo contra tu instalación antes de
  dártelo**: comprueba que los indicadores existan acá, que los sectores y
  mercados del filtro estén cargados, y te anticipa qué crearía y qué pisaría de
  lo que ya tenés. Es el mismo informe que ves en pantalla antes de decidir, y
  tampoco escribe nada — le sirve para corregir el archivo antes de entregártelo.

Y **no puede**:

- Ver nada que vos no veas. Si una estrategia es privada de otro usuario, para
  la IA tampoco existe.
- Crear, editar ni borrar señales. El catálogo de señales lo mantiene un
  administrador desde su pantalla — ver [Señales](/manual/configuracion-senales).
  La IA puede leerlas, explicarlas y sugerirte cambios, pero aplicarlos es
  siempre una decisión de una persona.
- Modificar ni borrar datos de ningún tipo.

Si la IA te propone una señal o una estrategia interesante, te la va a entregar
lista para que la lleves vos —descrita, o directamente como archivo—, pero
subirla e importarla es siempre una decisión tuya: no la carga sola.

## Si sos administrador

Tu token te da acceso de administrador, igual que tu sesión web: la IA que
conectes va a ver **todas** las señales y estrategias, incluidas las privadas
de otros usuarios. No es un permiso extra, es el mismo que ya tenés — pero vale
tenerlo presente al decidir dónde guardás ese token.
