# Truco Online — Definitive Edition

**Truco Online — Definitive Edition** es un videojuego multijugador online basado en el clásico juego de cartas argentino Truco.

El proyecto combina el juego en tiempo real con una plataforma web que permite a los usuarios gestionar sus cuentas, adquirir avatares mediante Mercado Pago y realizar donaciones.

La plataforma también incorpora un sistema de validación de pagos mediante webhooks y un sistema automatizado de reportes que permite recibir información sobre compras y donaciones a través de Telegram.

## Características

* Partidas multijugador de Truco en tiempo real.
* Sistema de usuarios y autenticación.
* Avatares desbloqueables mediante compras.
* Integración con Mercado Pago para procesar pagos.
* Sistema de donaciones con monto configurable.
* Validación de pagos mediante webhooks.
* Validación de firma de los webhooks mediante HMAC-SHA256.
* Verificación de los pagos directamente contra la API de Mercado Pago.
* Procesamiento idempotente de pagos para evitar duplicaciones.
* Registro de usuarios, partidas, movimientos, compras y donaciones.
* Reportes automatizados de ventas y donaciones mediante n8n y Telegram.
* Sitio web estático integrado con el backend.
* Juego desarrollado y exportado a HTML5 mediante GameMaker.

## Arquitectura

El sistema está compuesto por un backend, un sitio web, el juego HTML5, una base de datos y servicios externos para pagos y reportes.

| Componente     | Tecnología                |
| -------------- | ------------------------- |
| Backend        | Python + FastAPI          |
| Servidor       | Gunicorn + Uvicorn        |
| Frontend       | HTML, CSS y JavaScript    |
| Juego          | GameMaker HTML5           |
| Base de datos  | MySQL                     |
| Pagos          | Mercado Pago Checkout Pro |
| Automatización | n8n Cloud                 |
| Notificaciones | Telegram                  |

El backend funciona como núcleo de la aplicación. Se encarga de la autenticación, la lógica del juego, la gestión de usuarios, las compras, las donaciones y la comunicación con Mercado Pago.
El sitio web y el juego HTML5 son servidos directamente por el backend.

## Estructura del proyecto

```text
.
├── api.py
├── static/
│   ├── index.html
│   ├── js/
│   │   └── main.js
│   ├── styles.css
│   ├── perfiles/
│   └── developers/
├── game/
├── .env
├── .gitignore
└── README.md
```

### `api.py`

Archivo principal del backend. Contiene la aplicación FastAPI y la lógica relacionada con:

* API del juego.
* Autenticación de usuarios.
* Gestión de cuentas.
* Gestión de partidas.
* Registro de movimientos.
* Sistema de compras.
* Sistema de donaciones.
* Integración con Mercado Pago.
* Recepción y validación de webhooks.
* Comunicación con el sistema de reportes.

### `static/`

Contiene el sitio web de la plataforma.

Incluye:

* `index.html`: página principal y sección de contacto.
* `js/main.js`: lógica del frontend, incluyendo autenticación, tienda y donaciones.
* `styles.css`: estilos de la aplicación web.
* `perfiles/`: imágenes utilizadas para los perfiles y avatares.
* `developers/`: imágenes e información relacionada con el equipo de desarrollo.

### `game/`

Contiene la versión HTML5 compilada del juego desarrollado con GameMaker.

## Requisitos

Para ejecutar el proyecto se necesita:

* Python 3.10 o superior.
* MySQL Server.
* Un entorno virtual de Python.
* Las dependencias de Python utilizadas por el backend.
* Una cuenta de Mercado Pago para habilitar los pagos.
* Una cuenta de n8n Cloud únicamente si se desean utilizar los reportes automatizados.

Las principales dependencias utilizadas por el backend incluyen:

* FastAPI.
* Uvicorn.
* Gunicorn.
* MySQL Connector.
* Mercado Pago SDK.
* python-dotenv.

## Configuración

### 1. Variables de entorno

El proyecto utiliza variables de entorno para almacenar credenciales y parámetros de configuración.

Crear un archivo `.env` en la raíz del proyecto:

```env
# MySQL
MYSQL_HOST=127.0.0.1
MYSQL_USER=tu_usuario
MYSQL_PASSWORD=tu_password
MYSQL_DB=TrucoOnline

# Mercado Pago
MP_ACCESS_TOKEN=APP_USR-...
MP_WEBHOOK_SECRET=...
MP_CURRENCY=ARS
MP_NOTIFICATION_URL=https://tudominio.com/api/page_mp_webhook
MP_BACK_URL=https://tudominio.com/

# Precio de los avatares
AVATAR_PRECIO=2000

# Webhook de n8n
N8N_WEBHOOK_URL=
```

El archivo `.env` no debe incluirse en el repositorio.

Las credenciales de Mercado Pago, las credenciales de la base de datos y cualquier otro secreto deben mantenerse exclusivamente en las variables de entorno.

El backend carga estas variables mediante su sistema interno de configuración y conserva los valores que ya hayan sido definidos en el entorno.

### 2. Base de datos

El proyecto utiliza MySQL como sistema de almacenamiento.

La API se encarga de crear las tablas necesarias cuando no existen. Entre ellas se encuentran las relacionadas con:

* Usuarios.
* Avatares adquiridos.
* Órdenes de Mercado Pago.
* Donaciones.
* Partidas.
* Movimientos.

Solo es necesario disponer previamente de una base de datos y de un usuario de MySQL con los permisos correspondientes.

### 3. Mercado Pago

Para habilitar las compras y donaciones es necesario configurar una aplicación en Mercado Pago.

El proceso general es:

1. Crear una aplicación en el panel de desarrolladores de Mercado Pago.
2. Obtener el Access Token.
3. Configurar el secreto utilizado para validar los webhooks.
4. Definir la URL pública del endpoint de notificaciones.
5. Introducir los valores correspondientes en `.env`.

El endpoint utilizado por el proyecto es:

```text
POST /api/page_mp_webhook
```

También acepta solicitudes `GET` para el handshake correspondiente.

Cada operación de pago genera una referencia externa única mediante UUID. Esta referencia permite relacionar posteriormente la notificación recibida con la orden registrada en la base de datos.

## Ejecución local

Crear un entorno virtual:

```bash
python -m venv venv
```

Activarlo en Linux/macOS:

```bash
source venv/bin/activate
```

En Windows:

```powershell
venv\Scripts\activate
```

Instalar las dependencias:

```bash
pip install -r requirements.txt
```

Iniciar el servidor:

```bash
gunicorn api:app -k uvicorn.workers.UvicornWorker -b 127.0.0.1:8000
```

Una vez iniciado, la aplicación estará disponible en:

```text
http://127.0.0.1:8000
```

El backend sirve tanto el sitio web como el juego HTML5.

## Flujo de pagos

El sistema de pagos está diseñado para que el cliente no sea responsable de determinar si una compra debe considerarse válida.

El flujo es el siguiente:

1. El usuario selecciona un avatar o introduce un monto para realizar una donación.
2. El backend genera la operación correspondiente.
3. Para las compras de avatares, el precio es determinado por el servidor.
4. El backend crea una preferencia de pago en Mercado Pago.
5. Mercado Pago procesa el pago.
6. Mercado Pago envía una notificación al webhook del backend.
7. El backend valida la firma de la notificación.
8. El backend consulta directamente el pago en la API de Mercado Pago.
9. Se verifica el monto y la moneda recibidos contra la información registrada en el servidor.
10. La operación se marca como pagada.
11. Se aplica el efecto correspondiente, como otorgar un avatar.
12. Si está configurado n8n, se envía un evento para generar el reporte correspondiente.

La notificación enviada por Mercado Pago no se considera por sí misma una prueba suficiente de que el pago fue realizado. El backend consulta la API de Mercado Pago antes de aplicar cualquier efecto sobre la cuenta del usuario.

## Webhook de Mercado Pago

El endpoint utilizado para las notificaciones es:

```text
POST /api/page_mp_webhook
```

El handler realiza las siguientes comprobaciones:

1. Valida la firma `x-signature`.
2. Utiliza la plantilla:

```text
id:{data_id};request-id:{x_request_id};ts:{ts};
```

3. Calcula y verifica la firma mediante HMAC-SHA256.
4. Consulta el pago directamente a Mercado Pago.
5. Comprueba el monto y la moneda.
6. Comprueba que la operación corresponda a una orden registrada.
7. Marca la operación como pagada de manera idempotente.
8. Aplica la recompensa correspondiente.
9. Envía el evento al sistema de reportes cuando está configurado.

El procesamiento idempotente evita que una misma notificación pueda generar varias veces el mismo beneficio.

## Reportes automatizados

El proyecto puede integrarse con n8n para generar reportes automáticos de ventas y donaciones.

El flujo general es:

```text
Mercado Pago
      |
      v
Backend FastAPI
      |
      v
Webhook n8n
      |
      v
Consulta MySQL
      |
      v
Procesamiento
      |
      v
Telegram
```

Cuando una compra es confirmada, el backend puede enviar una solicitud `POST` al webhook configurado en `N8N_WEBHOOK_URL`.

n8n utiliza posteriormente una conexión de solo lectura con la base de datos para obtener la información necesaria y generar el reporte.

### Acceso recomendado a MySQL

Para el sistema de reportes se recomienda utilizar un usuario MySQL independiente y con permisos limitados.

Por ejemplo:

```text
n8n_ro
```

Este usuario debería disponer únicamente de permisos de lectura sobre las tablas necesarias para generar los reportes, como:

* `avatares_comprados`
* `donaciones_mp`
* `ordenes_mp`

El acceso desde n8n puede realizarse mediante un túnel SSH, evitando exponer públicamente el puerto `3306` de MySQL.

El flujo recomendado dentro de n8n es:

```text
Webhook → MySQL → Code → Telegram
```

## Seguridad

El proyecto incorpora varias medidas para reducir riesgos asociados a pagos y acceso a datos:

* Las credenciales de Mercado Pago se almacenan en variables de entorno.
* El archivo `.env` está excluido del repositorio.
* El precio de los avatares es determinado por el servidor.
* El cliente no puede establecer arbitrariamente el precio de una compra.
* Los webhooks de Mercado Pago se validan mediante firma.
* Los pagos se verifican directamente contra la API de Mercado Pago.
* Las operaciones se procesan de manera idempotente.
* n8n puede utilizar un usuario MySQL independiente con permisos de solo lectura.
* La conexión de n8n a MySQL puede realizarse mediante un túnel SSH.
* El puerto de MySQL no necesita estar expuesto públicamente.

## Autores

### Ismael Becker

Game Developer y Fullstack Developer.

Responsable del desarrollo del juego, frontend, backend e integración general de la plataforma.

### Joaquin Sedoff

Desarrollador Python y Fullstack Developer.

Responsable del desarrollo backend, infraestructura y sistemas distribuidos.

La información de contacto y los datos de los desarrolladores están disponibles en la sección **Contacto** del sitio web.

---

**Becker Ismael, Joaquin Sedoff — 2026**
