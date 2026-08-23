Actuá como un ingeniero de software senior encargado de integrar Mercado Pago dentro de un juego de Truco Online desarrollado con GameMaker.

IMPORTANTE: antes de escribir código, inspeccioná completamente el repositorio que tenés disponible. No asumas una arquitectura, estructura de carpetas, sistema de autenticación, ORM, base de datos ni modelos que todavía no hayas verificado. El backend existente utiliza Flask en Python y debe ser, salvo que exista una razón técnica fuerte en contra, el mismo backend que gestione Mercado Pago. No queremos crear un backend Node.js paralelo.

## Contexto del proyecto

El proyecto es un juego de Truco Online desarrollado en GameMaker. Tendrá cuentas de usuario y partidas entre jugadores.

Queremos incorporar microtransacciones para vender elementos cosméticos, inicialmente skins de cartas. Como caso inicial de prueba puede considerarse una skin con un precio aproximado de ARS 500.

Mercado Pago fue elegido porque el mercado inicial del juego es Argentina.

La integración deseada utiliza Checkout Pro: el backend crea la compra, GameMaker recibe una URL de Checkout Pro y el jugador realiza el pago fuera del juego mediante Mercado Pago.

La autoridad sobre compras, precios y propiedad de skins debe estar SIEMPRE en el servidor. GameMaker debe considerarse un cliente no confiable.

## Trabajo previo ya realizado

Antes de integrar esto al backend Flask se desarrolló un prototipo independiente en Node.js para comprender y validar la API de Mercado Pago.

Ese prototipo ya consiguió exitosamente:

1. Crear una Preference de Checkout Pro mediante:

POST https://api.mercadopago.com/checkout/preferences

utilizando un Access Token almacenado en variables de entorno.

2. Crear una compra sandbox de:

Skin: "Skin Cartas Rojas"
Precio: ARS 500
Cantidad: 1
external_reference: "ORDER-TEST-001"

3. Recibir correctamente el preference_id y sandbox_init_point.

4. Abrir Checkout Pro Sandbox con una cuenta compradora de prueba y completar pagos ficticios.

5. Consultar un Payment directamente mediante:

GET https://api.mercadopago.com/v1/payments/{payment_id}

y verificar correctamente datos como:

status = approved
transaction_amount = 500
currency_id = ARS
external_reference = ORDER-TEST-001

6. Exponer temporalmente localhost mediante ngrok.

7. Configurar un endpoint de Webhooks.

8. Recibir correctamente Webhooks enviados desde el simulador oficial de Mercado Pago.

9. Validar correctamente la firma x-signature del Webhook utilizando la secret key configurada en Mercado Pago.

10. Obtener data.id del Webhook, consultar posteriormente el Payment directamente en la API de Mercado Pago y verificar:

* firma válida;
* payment existente;
* status approved;
* monto correcto;
* moneda correcta;
* external_reference correcta.

Por lo tanto, NO necesitamos investigar desde cero cómo funciona Mercado Pago. El objetivo ahora es trasladar esta prueba conceptual al backend Flask real del juego de una manera correctamente diseñada.

## Objetivo funcional

Queremos implementar aproximadamente este flujo:

Jugador autenticado en GameMaker
→ selecciona una skin
→ GameMaker solicita iniciar compra al backend Flask
→ Flask identifica al usuario autenticado
→ Flask obtiene internamente producto y precio
→ Flask crea una orden propia en estado pending
→ Flask crea una Preference en Mercado Pago
→ external_reference contiene el identificador único de nuestra orden
→ Flask devuelve checkout_url a GameMaker
→ GameMaker abre Checkout Pro
→ jugador paga
→ Mercado Pago genera/actualiza Payment
→ Mercado Pago envía Webhook al backend
→ Flask valida la firma del Webhook
→ Flask obtiene payment_id
→ Flask consulta el Payment directamente a Mercado Pago
→ Flask identifica nuestra orden mediante external_reference
→ Flask verifica todos los datos
→ si todo es válido, marca la orden como pagada
→ Flask habilita la skin para ese usuario
→ GameMaker puede consultar el estado de la compra o las skins pertenecientes al usuario.

## Principio fundamental de seguridad

NO confiar en información sensible enviada desde GameMaker.

Por ejemplo, GameMaker puede enviar:

{
"skin_id": "cartas_rojas"
}

Pero NO debe decidir:

{
"skin_id": "cartas_rojas",
"price": 500,
"payment_approved": true
}

El precio debe obtenerse exclusivamente desde información controlada por el servidor.

Un cliente modificado no debe poder comprar una skin de ARS 500 enviando price=1 ni habilitar una skin diciendo que un pago fue aprobado.

## Primera tarea: analizar el repositorio

Antes de realizar modificaciones:

1. Inspeccioná la estructura completa del proyecto Flask.

2. Identificá:

* entrypoint de Flask;
* blueprints existentes;
* configuración;
* sistema de autenticación;
* modelo de usuarios;
* base de datos utilizada;
* ORM utilizado, si existe;
* sistema de migraciones;
* forma actual de definir endpoints;
* variables de entorno;
* manejo de errores;
* estructura de servicios/helpers;
* forma en que GameMaker actualmente consume la API;
* convenciones del proyecto.

3. Buscá si ya existe algún concepto equivalente a:

* productos;
* inventario de jugador;
* cosméticos;
* skins;
* compras;
* transacciones.

4. Antes de programar, explicá brevemente qué encontraste y proponé cómo integrar Mercado Pago respetando la arquitectura existente.

NO crees estructuras duplicadas si el proyecto ya tiene mecanismos equivalentes.

## Modelo conceptual

Si el proyecto todavía no posee estructuras equivalentes, necesitaremos conceptualmente algo similar a:

Order

* id
* user_id
* product_id o skin_id
* amount
* currency
* status
* mp_preference_id
* mp_payment_id
* created_at
* paid_at

Y una relación de propiedad similar a:

UserSkin

* user_id
* skin_id
* unlocked_at

Estos nombres NO son obligatorios. Adaptalos a las convenciones existentes.

Sería conveniente que Order.id sea un identificador difícil de predecir, por ejemplo UUID.

Los estados podrían ser conceptualmente:

pending
paid
failed
cancelled

pero adaptalos si la aplicación ya tiene una estrategia distinta.

## Catálogo y precios

Debe existir una fuente confiable del lado servidor que permita resolver:

cartas_rojas → ARS 500

Puede ser una tabla Product/Skin, configuración existente o estructura equivalente.

El cliente NO debe ser la autoridad del precio.

## Endpoint para iniciar una compra

Implementar, adaptándolo a las convenciones existentes, algo conceptualmente equivalente a:

POST /store/checkout

El usuario debe estar autenticado utilizando el mecanismo que ya posea el juego.

Entrada aproximada:

{
"skin_id": "cartas_rojas"
}

El backend debe:

1. identificar al usuario autenticado;
2. comprobar que la skin existe;
3. obtener el precio del servidor;
4. comprobar opcionalmente que el jugador todavía no posee la skin;
5. crear una Order pending;
6. crear una Preference de Mercado Pago;
7. utilizar Order.id como external_reference;
8. guardar mp_preference_id;
9. devolver al cliente algo equivalente a:

{
"order_id": "...",
"checkout_url": "..."
}

NO devolver Access Tokens ni secretos al cliente.

## Integración con Mercado Pago

Las credenciales deben obtenerse mediante variables de entorno.

Por ejemplo:

MP_ACCESS_TOKEN
MP_WEBHOOK_SECRET

Nunca hardcodearlas.

Nunca exponerlas a GameMaker.

Utilizar preferentemente el SDK oficial de Mercado Pago para Python cuando resulte razonable, pero no introducir dependencias innecesarias si una llamada HTTP simple resulta más coherente con el proyecto.

Si se utiliza el SDK oficial, usar su versión y APIs actualmente soportadas.

## Webhook

Implementar un endpoint conceptualmente equivalente a:

POST /webhooks/mercadopago

El endpoint debe:

1. recibir la notificación;
2. validar la firma x-signature utilizando MP_WEBHOOK_SECRET;
3. rechazar notificaciones cuya firma no sea válida;
4. identificar el tipo de evento;
5. obtener data.id/payment_id;
6. responder adecuadamente a Mercado Pago;
7. consultar posteriormente el Payment directamente a la API de Mercado Pago.

NO tomar el contenido del Webhook como prueba suficiente de pago.

El Webhook sirve principalmente como notificación de que algo cambió.

La fuente confiable para conocer el estado final del pago debe ser la API de Mercado Pago.

## Validación del Payment

Una vez obtenido el Payment desde Mercado Pago, comprobar al menos:

payment.status == "approved"

payment.external_reference corresponde a una Order válida de nuestra base de datos.

payment.transaction_amount coincide EXACTAMENTE con el amount almacenado en nuestra Order.

payment.currency_id coincide con la moneda esperada.

La Order pertenece a un usuario válido.

El producto asociado a la Order es el correcto.

Guardar también payment.id.

Si alguna validación falla, NO habilitar ninguna skin.

No utilizar únicamente una redirección de Checkout Pro o una pantalla de "pago exitoso" como prueba de pago.

## Idempotencia

Este punto es MUY IMPORTANTE.

Mercado Pago puede enviar una misma notificación más de una vez.

El sistema debe soportar:

Webhook Payment 123
→ procesa compra
→ habilita skin

Webhook Payment 123 nuevamente
→ detecta que la compra ya fue procesada
→ no duplica operaciones
→ no genera errores.

Diseñar la base de datos y la lógica para que procesar el mismo payment_id múltiples veces sea seguro.

Si es adecuado para la arquitectura existente, utilizar constraints únicos sobre campos como mp_payment_id o relaciones user_id + skin_id.

## Concurrencia

Considerar también que dos Webhooks o procesos podrían intentar confirmar una misma Order casi simultáneamente.

Utilizar transacciones de base de datos o mecanismos equivalentes cuando sea necesario para evitar duplicar desbloqueos.

## Habilitación de la skin

Solamente después de verificar correctamente el Payment:

Order.status = paid

y asociar:

usuario → skin

Guardar, si corresponde:

paid_at
mp_payment_id
unlocked_at

La operación debería ser transaccional si la base de datos utilizada lo permite.

## Consulta desde GameMaker

Evaluar cuál se adapta mejor al backend existente.

Una alternativa es:

GET /store/orders/{order_id}

Respuesta:

{
"status": "pending"
}

o:

{
"status": "paid"
}

Otra alternativa complementaria:

GET /users/me/skins

Respuesta:

{
"skins": [
"default",
"cartas_rojas"
]
}

La lista definitiva de skins habilitadas debe provenir del servidor.

No confiar en que GameMaker conserve localmente el estado como fuente de verdad.

## Integración futura con GameMaker

No hace falta implementar código GML hasta que la parte Flask esté correctamente funcionando.

Pero diseñar la API pensando en que GameMaker posteriormente deberá:

1. llamar POST /store/checkout;
2. recibir checkout_url;
3. abrir esa URL en navegador;
4. esperar;
5. consultar periódicamente el estado de Order o actualizar el inventario;
6. cuando el backend indique paid, mostrar la skin como disponible.

GameMaker nunca utilizará directamente MP_ACCESS_TOKEN.

Toda comunicación sensible con Mercado Pago ocurre entre Flask y Mercado Pago.

## Sandbox

La integración debe soportar inicialmente el entorno de prueba de Mercado Pago.

Ya sabemos que:

* se pueden crear Preferences sandbox;
* se pueden realizar Payments ficticios;
* esos Payments pueden consultarse mediante la API;
* el simulador oficial de Webhooks puede enviar una notificación firmada con un payment_id real del sandbox;
* la firma ya fue validada exitosamente en el prototipo previo.

Por lo tanto, crear un procedimiento de prueba reproducible para verificar el nuevo código Flask.

Idealmente:

crear usuario/prueba
→ iniciar checkout
→ obtener URL
→ realizar pago sandbox
→ obtener payment_id
→ utilizar simulador oficial de Webhooks con ese ID
→ Flask recibe Webhook
→ verifica firma
→ consulta Payment
→ encuentra Order mediante external_reference
→ cambia Order a paid
→ agrega skin al usuario
→ endpoint del usuario muestra la nueva skin.

## Logging

Agregar logs útiles, pero NO imprimir:

MP_ACCESS_TOKEN
MP_WEBHOOK_SECRET
contraseñas
tokens de sesión
datos sensibles.

Logs útiles podrían ser:

Order creada: UUID
Preference creada
Webhook recibido
Payment ID
Order identificada
Payment aprobado/rechazado
Order marcada como paid
Skin habilitada

## Manejo de errores

Implementar errores claros para situaciones como:

skin inexistente;
skin ya comprada;
error de Mercado Pago;
Preference no creada;
Order inexistente;
Payment inexistente;
monto incorrecto;
moneda incorrecta;
external_reference incorrecta;
firma Webhook inválida;
Payment pendiente/rechazado;
Webhook duplicado.

No marcar una compra como paid ante errores ambiguos.

## Dependencias

No agregues una infraestructura grande para resolver un problema pequeño.

Respetá las herramientas que ya utiliza el proyecto.

Si usa SQLAlchemy, utilizá SQLAlchemy.

Si usa Flask-Migrate/Alembic, generá la migración correspondiente.

Si tiene Blueprints, integralo mediante Blueprints.

Si tiene capa de services, mantené esa separación.

No reestructures todo el backend salvo que exista una razón realmente necesaria.

## Calidad del código

Queremos una integración mantenible y apta para producción posteriormente.

Priorizar:

* separación de responsabilidades;
* funciones pequeñas;
* nombres claros;
* configuración mediante environment;
* manejo correcto de excepciones;
* código testeable;
* evitar duplicación;
* seguridad;
* idempotencia;
* integración mínima con el código existente.

## Muy importante: no hagas cambios masivos sin explicar

Trabajá de forma incremental.

Primero analizá.

Después presentá el plan.

Luego implementá por etapas.

Después de cada etapa relevante, explicá:

* qué modificaste;
* por qué;
* qué archivos tocaste;
* cómo probarlo;
* qué resultado deberíamos obtener.

No inventes información sobre el proyecto que no hayas encontrado en el repositorio.

Si existe una decisión de arquitectura que no puede resolverse inspeccionando el código, señalala explícitamente y elegí la opción más conservadora.

## Resultado esperado

Al terminar esta primera integración deberíamos tener:

1. Un usuario autenticado del juego.

2. Una skin/producto definida en servidor.

3. Un endpoint Flask para iniciar la compra.

4. Una Order única guardada en base de datos.

5. Una Preference de Checkout Pro relacionada mediante external_reference.

6. Una checkout_url enviada a GameMaker/cliente.

7. Un endpoint Webhook seguro.

8. Validación de x-signature.

9. Consulta server-to-server del Payment.

10. Verificación de status, amount, currency y external_reference.

11. Procesamiento idempotente.

12. Order marcada como paid.

13. Skin asociada permanentemente al usuario.

14. Un endpoint que permita verificar que el usuario posee esa skin.

15. Un procedimiento documentado para probar todo en Mercado Pago Sandbox.

Comenzá inspeccionando el repositorio y NO escribas código todavía. Primero describime brevemente la arquitectura que encontraste y proponé dónde integrarías cada componente de Mercado Pago.
