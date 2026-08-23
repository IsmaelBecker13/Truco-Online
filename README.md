Truco Online — Definitive Edition

Juego multijugador online de Truco con tienda de avatares de pago, donaciones y
reportes automáticos. El backend expone la API de juego y la integración con
Mercado Pago; el front-end es un sitio estático que incluye el juego HTML5
(hecho en GameMaker).

Características

- Partidas multijugador de Truco en tiempo real.
- Avatares premium (desbloqueables mediante pago con Mercado Pago).
- Donaciones con monto configurable.
- Confirmación de pagos vía webhook de Mercado Pago con validación de firma.
- Reportes diarios y en tiempo real de ventas/donaciones vía n8n -> Telegram.

Stack técnico

Capa        Tecnología
Backend     Python + FastAPI (api.py)
Servidor    gunicorn + workers uvicorn.workers.UvicornWorker
Frontend    HTML/CSS/JS estático (static/)
Juego       GameMaker HTML5 (game/)
Base de datos MySQL
Pagos       Mercado Pago (Checkout Pro)
Reportes    n8n Cloud (webhook + túnel SSH a MySQL -> Telegram)

Estructura del proyecto

.
├── api.py                 # API FastAPI: juego, auth, MP, webhook, reportes
├── static/                # Sitio web estático
│   ├── index.html         # Página principal + sección de contacto
│   ├── js/main.js         # Lógica del front-end (login, tienda, donar, etc.)
│   ├── styles.css
│   ├── perfiles/          # Imágenes de perfiles/avatares
│   └── developers/        # Fotos del equipo de desarrollo
├── game/                  # Build HTML5 del juego (GameMaker)
├── .env                   # Variables de entorno (NO versionado)
├── .gitignore
└── README.md

Requisitos

- Python 3.10+
- MySQL Server
- Un entorno virtual (venv) con las dependencias (FastAPI, uvicorn,
  gunicorn, mysql-connector, mercadopago, python-dotenv, etc.)
- Cuenta de Mercado Pago (token de acceso y secreto de webhook).
- (Opcional) Cuenta n8n Cloud para reportes.

Configuración

1. Variables de entorno

Creá un archivo .env en la raíz (ya está en .gitignore) con este formato:

  # MySQL
  MYSQL_HOST=127.0.0.1
  MYSQL_USER=tu_usuario
  MYSQL_PASSWORD=tu_password
  MYSQL_DB=TrucoOnline

  # Mercado Pago (NO subir al repo)
  MP_ACCESS_TOKEN=APP_USR-...
  MP_WEBHOOK_SECRET=...
  MP_CURRENCY=ARS
  MP_NOTIFICATION_URL=https://tudominio.com/api/page_mp_webhook
  MP_BACK_URL=https://tudominio.com/

  # Precio de los avatares de pago (lo define el servidor)
  AVATAR_PRECIO=2000

  # Webhook de n8n que se dispara al confirmar una compra (dejar vacío para desactivar)
  N8N_WEBHOOK_URL=

  ⚠️ Nunca commitees el .env. El código lo carga con _cargar_env() y solo
  completa las variables que no estén ya en el entorno.

2. Base de datos

La API crea las tablas automáticamente si no existen
(usuarios, avatares_comprados, ordenes_mp, donaciones_mp, partidas,
movimientos, etc.). Solo necesitás crear la base de datos y el usuario MySQL.

3. Mercado Pago

- Creá la app en el panel de Mercado Pago y copiá el Access Token.
- Configurá el webhook en "Your integrations -> Webhooks" apuntando a
  MP_NOTIFICATION_URL y copiá el secret signature en MP_WEBHOOK_SECRET.
- El flujo de pago crea una preferencia con un external_reference único
  (UUID) que luego se usa para conciliar el pago en el webhook.

Ejecución local

  python -m venv venv
  source venv/bin/activate        # Windows: venv\Scripts\activate
  pip install -r requirements.txt # ajustá según tus dependencias
  gunicorn api:app -k uvicorn.workers.UvicornWorker -b 127.0.0.1:8000

La API queda en http://127.0.0.1:8000. El sitio estático y el juego se sirven
desde la propia aplicación (/ y /game).

Webhook de Mercado Pago

Endpoint: POST /api/page_mp_webhook (también acepta GET para el handshake).

El handler:

1. Valida la firma x-signature (plantilla
   id:{data_id};request-id:{x_request_id};ts:{ts};, HMAC-SHA256 en hex).
2. Consulta el pago a la API de MP (la notificación no es prueba de pago).
3. Verifica monto y moneda contra lo registrado (el servidor es la autoridad).
4. Marca la orden/donación como pagada de forma idempotente.
5. Dispara N8N_WEBHOOK_URL en segundo plano para el reporte en tiempo real.

Reportes con n8n

Flujo: al confirmarse una compra, la API hace POST a un webhook de n8n ->
n8n consulta la base por un túnel SSH (usuario de solo lectura) y envía el
reporte a Telegram.

Recomendado:

- Usar un usuario MySQL de solo lectura (n8n_ro) con acceso limitado a
  avatares_comprados, donaciones_mp y ordenes_mp.
- Conectar n8n a MySQL mediante túnel SSH (sin exponer el puerto 3306).
- En n8n: Webhook -> MySQL -> Code -> Telegram.

Seguridad

- Las credenciales de MP viven solo en .env (gitignore).
- El precio de los avatares lo fija el servidor; el cliente nunca lo envía.
- El webhook valida firma y concilia contra la API de MP antes de aplicar
  cualquier efecto en el juego.
- n8n accede a la DB por túnel SSH con un usuario de solo lectura.

Autores

- Ismael Becker — Game developer / Fullstack.
- Joaquin Sedoff — Desarrollador Python / Fullstack, infraestructura y
  sistemas distribuidos.

Ver sus datos en la sección Contacto del sitio (static/index.html).


Becker Ismael, Joaquin Sedoff - 2026
