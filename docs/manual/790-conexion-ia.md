---
slug: conexion-ia
title: Conexión IA
chapter: 7. Configuración
order: 790
roles: analista
page: /ia
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

En tu programa de IA vas a tener que agregar una conexión —según cuál uses, la
va a llamar *conector*, *extensión* o *aplicación personalizada*— y pegarle la
dirección de este servicio. **No es la misma dirección con la que entrás a la
aplicación**: es una aparte, y te la da el administrador.

> **Pegala tal cual, terminada en `/mcp`, y no le agregues nada más.** Es el
> error más común y el más difícil de darse cuenta, porque el programa no dice
> que la dirección esté mal: dice que no pudo conectarse, o que tenés que
> vincular la cuenta. Si te pasa, lo primero que hay que revisar es la
> dirección.

Cuando la agregues, tu programa de IA va a abrir una página de esta plataforma
pidiéndote autorización. **Ahí va el token, no tu usuario y contraseña** — esta
conexión nunca te pide la contraseña. Pegás el token, autorizás, y el programa
queda conectado hasta que lo revoques.

## Qué puede hacer la IA con tu token

Puede **leer** exactamente lo que vos podrías ver entrando a la aplicación:

- El catálogo de indicadores, señales y estrategias que tenés a la vista.
- El ranking de una estrategia en una fecha, y cómo evolucionó el puntaje de un
  activo.
- El manual, para explicarte cómo funciona cada cálculo de este sistema en
  particular.

Y **no puede**:

- Ver nada que vos no veas. Si una estrategia es privada de otro usuario, para
  la IA tampoco existe.
- Crear, editar ni borrar señales. El catálogo de señales lo mantiene un
  administrador desde su pantalla — ver [Señales](/manual/configuracion-senales).
  La IA puede leerlas, explicarlas y sugerirte cambios, pero aplicarlos es
  siempre una decisión de una persona.
- Modificar ni borrar datos de ningún tipo.

Si la IA te propone una señal o una estrategia interesante, te la va a describir
para que la lleves vos: no la carga sola.

## Si sos administrador

Tu token te da acceso de administrador, igual que tu sesión web: la IA que
conectes va a ver **todas** las señales y estrategias, incluidas las privadas
de otros usuarios. No es un permiso extra, es el mismo que ya tenés — pero vale
tenerlo presente al decidir dónde guardás ese token.
