import os
import re
import uuid
import hmac
import hashlib
import base64
from datetime import datetime, timedelta
import logging
from fastapi import FastAPI, Query, HTTPException, Response, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from werkzeug.security import check_password_hash, generate_password_hash
import mysql.connector
import requests
import threading

from mysql.connector import Error

def _cargar_env():
    """Carga variables de entorno desde un archivo .env (no versionado) ubicado
    al lado de este archivo. No sobreescribe variables ya presentes en el entorno."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            clave, valor = line.split("=", 1)
            clave = clave.strip()
            valor = valor.strip().strip('"').strip("'")
            if clave and clave not in os.environ:
                os.environ[clave] = valor


_cargar_env()

app = FastAPI(root_path="/api") # Iniciar la aplicación FastAPI

def obtener_conexion():
    return mysql.connector.connect(
        host=os.environ["MYSQL_HOST"],
        user=os.environ["MYSQL_USER"],
        password=os.environ["MYSQL_PASSWORD"],
        database=os.environ["MYSQL_DB"]
    )

logger = logging.getLogger("uvicorn.error")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)


@app.get("/login")  # Inicia Sesion en el juego
def login(usuario: str = Query(...), contrasena: str = Query(...), session_id: str = Query(...)):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        #logger.info(f"[login] Parámetros recibidos -> usuario: {usuario}, session_id: {session_id}")
        
        # Verificar si el usuario existe
        cursor.execute("SELECT * FROM usuarios WHERE usuario = %s", (usuario,))
        resultado = cursor.fetchone()
        if not resultado:
            #logger.warning(f"[login] Usuario no encontrado: {usuario}")
            return "000"  # Credenciales inválidas

        id, usuario, hash_almacenado, exp, estado, ultima_actividad, foto_perfil, session_id_actual = resultado

        # Validar contraseña
        if not check_password_hash(hash_almacenado, contrasena):
            #logger.warning(f"[login] Contraseña incorrecta para usuario: {usuario}")
            return "000"

        # Si el usuario ya está activo
        if estado == 1:
            if session_id_actual != session_id:
                #logger.info(f"[login] Sesión duplicada para usuario: {usuario} (session_id actual: {session_id_actual}, enviado: {session_id})")
                return "010"  # Usuario ya activo con otra sesión

        # Actualizar actividad, estado y session_id
        ahora = datetime.utcnow() - timedelta(hours=3)
        cursor.execute("""
            UPDATE usuarios 
            SET ultima_actividad = %s, estado = 1, session_id = %s 
            WHERE id = %s
        """, (ahora, session_id, id))

        conexion.commit()
        #logger.info(f"[login] Usuario {usuario} ha iniciado sesión correctamente")
        return {"exp": exp}

    except Error as e:
        logger.error(f"[login] Error al conectar a la BD: {e}")
        raise HTTPException(status_code=500, detail="Error de servidor")

    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

@app.get("/actividad")  # Endpoint para actualizar la última actividad del usuario
def actividad(usuario: str = Query(...), session_id: str = Query(...)):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        #logger.info(f"[actividad] Heartbeat de {usuario} con session_id: {session_id}")

        # Verificar que el usuario exista y que la sesión coincida
        cursor.execute("SELECT id, session_id FROM usuarios WHERE usuario = %s", (usuario,))
        resultado = cursor.fetchone()
        if not resultado:
            #logger.warning(f"[actividad] Usuario no encontrado: {usuario}")
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        id_usuario, session_id_db = resultado

        if session_id != session_id_db:
            #logger.warning(f"[actividad] Session ID inválido para {usuario} (esperado: {session_id_db}, recibido: {session_id})")
            return {"status": "invalid_session"}

        # Actualizar última actividad y estado
        hora_actual = (datetime.utcnow() - timedelta(hours=3)).strftime('%Y-%m-%d %H:%M:%S')
        cursor.execute("""
            UPDATE usuarios SET ultima_actividad = %s, estado = 1 WHERE id = %s
        """, (hora_actual, id_usuario))
        conexion.commit()
        #logger.info(f"[actividad] Actividad actualizada para {usuario}")

        # Contar usuarios online
        cursor.execute("SELECT COUNT(*) FROM usuarios WHERE estado = 1")
        num_usuarios_online = cursor.fetchone()[0]

        return {"status": "ok", "online_users": num_usuarios_online}

    except Error as e:
        #logger.error(f"[actividad] Error al conectar a la BD: {e}")
        raise HTTPException(status_code=500, detail="Error de servidor")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

@app.get("/actualizar_exp")  # Endpoint para actualizar la experiencia del usuario
def actualizar_exp(usuario: str = Query(...), exp: int = Query(...)):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        #logger.info(f"[actualizar_exp] Actualizando la experiencia para usuario: {usuario}")
        # Verificar que el usuario exista
        cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", (usuario,))
        resultado = cursor.fetchone()
        if not resultado:
            #logger.warning(f"[actualizar_exp] Usuario no encontrado: {usuario}")
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        id_usuario = resultado[0]
        # Actualizar experiencia
        cursor.execute("UPDATE usuarios SET exp = %s WHERE id = %s", (exp, id_usuario))
        conexion.commit()
        #logger.info(f"[actualizar_exp] Experiencia actualizada para {usuario}")
        return {"status": "ok"}
    except Error as e:
        logger.error(f"[actualizar_exp] Error al conectar a la BD: {e}")
        raise HTTPException(status_code=500, detail="Error de servidor")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

@app.get("/buscar") # Busca una partida abierta o crea una nueva si no hay partidas abiertas
def buscar(usuario: str = Query(...), mazo: str = Query(...)):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        #logger.info(f"[buscar] Parámetros recibidos -> usuario: {usuario}, mazo: {mazo}")
        # Obtener solo ID usuario por nombre
        cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", (usuario,))
        id = cursor.fetchone()
        if id is None:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        id = id[0]  # Extraer el ID del resultado
        # Verificar si usuario está en partidas con jugador2 o jugador1 = 0
        cursor.execute("SELECT  id FROM partidas WHERE (jugador1 = %s OR jugador2 = %s) AND estado = 0", (id, id))
        partida_id = cursor.fetchone()
        if partida_id is not None:
            #logger.info(f"[buscar] Partida existente para usuario {usuario}: {partida_id[0]}")
            # Eliminar partida existente
            cursor.execute("DELETE FROM partidas WHERE id = %s", (partida_id[0],))
            conexion.commit()  # Confirma los cambios en la base de datos
            #logger.info(f"[buscar] Partida {partida_id[0]} eliminada")
        # Buscar partida abierta (estado = 0 y jugador1 o jugador2 = 0)
        cursor.execute("SELECT id FROM partidas WHERE (jugador1 = 0 OR jugador2 = 0) AND estado = 0")
        partida_abierta = cursor.fetchone()
        if partida_abierta is not None: # Caso en donde hay una partida abierta, ya sea con el jugador1 o el jugador2 vacío
            # Verificar si jugador2 está vacío
            id_partida = partida_abierta[0]
            cursor.execute("SELECT jugador2 FROM partidas WHERE id = %s AND jugador2 = 0", (id_partida,))
            jugador2_vacio = cursor.fetchone()
            if jugador2_vacio is not None: # Caso en donde jugador2 está vacío
                # Actualizar jugador2 y mazo2
                cursor.execute("UPDATE partidas SET jugador2 = %s, mazo2 = %s WHERE id = %s", (id, mazo, id_partida))
                #logger.info(f"[buscar] Actualizado jugador2 y mazo2 en partida {id_partida}")
            else: # Caso en donde jugador1 está vacío
                cursor.execute("UPDATE partidas SET jugador1 = %s, mazo1 = %s WHERE id = %s", (id, mazo, id_partida))
                #logger.info(f"[buscar] Actualizado jugador1 y mazo1 en partida {id_partida}")
            conexion.commit()  # Confirma los cambios en la base de datos
        else: # Caso en donde no hay partidas abiertas
            # Crear nueva partida con jugador1
            cursor.execute("INSERT INTO partidas (jugador1, mazo1) VALUES (%s, %s)", (id, mazo))
            conexion.commit()  # Confirma los cambios en la base de datos
            id_partida = cursor.lastrowid  # Obtiene el ID de la última inserción
            #logger.info(f"[buscar] Nueva partida creada con id: {id_partida}")
        return {"id_partida": id_partida}
    except Error as e:
        print(f"[buscar] Error al conectar a la BD: {e}")
        logger.error(f"[buscar] Error al conectar a la BD: {e}")
        raise HTTPException(status_code=500, detail="Error de servidor")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

@app.get("/verificar")  # Verifica si una partida está lista o en espera
def verificar(id_partida: int = Query(...), usuario: str = Query(...)):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        #logger.info(f"[verificar] Parámetros recibidos -> id_partida: {id_partida}, usuario: {usuario}")
        # Obtener ID del usuario
        cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", (usuario,))
        resultado_usuario = cursor.fetchone()
        if resultado_usuario is None:
            #logger.info(f"[verificar] Usuario no encontrado: {usuario}")
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        id_usuario = resultado_usuario[0]
        #logger.info(f"[verificar] ID usuario obtenido: {id_usuario}")
        # Obtener datos de la partida
        cursor.execute("SELECT jugador1, jugador2, mazo1, mazo2, estado FROM partidas WHERE id = %s", (id_partida,))
        partida = cursor.fetchone()
        if not partida:
            #logger.info(f"[verificar] Partida no encontrada: {id_partida}")
            raise HTTPException(status_code=404, detail="Partida no encontrada")
        jugador1, jugador2, mazo1, mazo2, estado = partida
        #logger.info(f"[verificar] Datos partida: jugador1={jugador1}, jugador2={jugador2}, estado={estado}")
        # Determinar rival y su mazo
        if jugador1 != id_usuario:
            rival_id = jugador1
            mazo_rival = mazo1
        else:
            rival_id = jugador2
            mazo_rival = mazo2
        #logger.info(f"[verificar] Rival: {rival_id}, Mazo rival: {mazo_rival}")
        # Obtener datos del rival (si existe)
        if not rival_id or rival_id == 0:
            #logger.info(f"[verificar] Rival aún no asignado o no existe")
            rival_usuario = None
            rival_exp = None
        else:
            cursor.execute("SELECT usuario, exp FROM usuarios WHERE id = %s", (rival_id,))
            rival = cursor.fetchone()
            if rival:
                rival_usuario, rival_exp = rival
            else:
                rival_usuario = None
                rival_exp = None
                #logger.info(f"[verificar] Rival no encontrado en tabla usuarios: {rival_id}")
        # Verificar estado (si no está lista)
        if estado == 0:
            #logger.info("[verificar] Partida no está lista (estado == 0)")
            return {"estado": 0}
        # Determinar quién empieza
        id_empieza = jugador1 if estado == 1 else jugador2
        cursor.execute("SELECT usuario FROM usuarios WHERE id = %s", (id_empieza,))
        empieza = cursor.fetchone()
        nombre_empieza = empieza[0] if empieza else None
        #logger.info(f"[verificar] Empieza la partida: {nombre_empieza}")
        return {
            "estado": estado,
            "nombre_empieza": nombre_empieza,
            "nombre_rival": rival_usuario,
            "exp_rival": rival_exp,
            "mazo_rival": mazo_rival,
        }
    except Error as e:
        logger.error(f"[verificar] Error al conectar a la BD: {e}")
        raise HTTPException(status_code=500, detail="Error de servidor")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()



@app.get("/cancelar") # Cancelar la busqueda de partida
def cancelar(usuario: str = Query(...), id_partida: int = Query(...)):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        #logger.info(f"[cancelar] Parámetros recibidos -> id_partida: {id_partida}, usuario: {usuario}")
        # Obtener solo ID usuario por nombre
        cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", (usuario,))
        id = cursor.fetchone()
        if id is None:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        id = id[0]  # Extraer el ID del resultado
        #logger.info(f"[cancelar] ID usuario obtenido: {id}")
        # Verificar Actividad de la partida
        cursor.execute("SELECT estado FROM partidas WHERE id = %s", (id_partida,))
        partida = cursor.fetchone()
        if not partida:
            #logger.info(f"[cancelar] Partida no encontrada: {id_partida}")
            raise HTTPException(status_code=404, detail="Partida no encontrada")
        estado = partida[0]
        #logger.info(f"[cancelar] Estado de la partida: {estado}")
        if estado == 0:
            # Actualizar jugador1 o jugador2 a 0 si coincide con usuario_id
            cursor.execute("UPDATE partidas SET jugador1 = 0 WHERE id = %s AND jugador1 = %s", (id_partida, id))
            cursor.execute("UPDATE partidas SET jugador2 = 0 WHERE id = %s AND jugador2 = %s", (id_partida, id))
            conexion.commit()
            #logger.info(f"[cancelar] Partida {id_partida} cancelada para usuario {usuario}")
        return {"estado": estado}
    except Error as e:
        print(f"[cancelar] Error al conectar a la BD: {e}")
        logger.error(f"[cancelar] Error al conectar a la BD: {e}")
        raise HTTPException(status_code=500, detail="Error de servidor")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

@app.get("/envio") # Envía un movimiento a la base de datos
def envio(usuario: str = Query(...), id_partida: int = Query(...), movimiento: str = Query(...)):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        # Obtener solo ID usuario por nombre
        cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", (usuario,))
        user_id = cursor.fetchone()
        if user_id is None:
            #logger.error(f"[envio] Usuario no encontrado: {usuario}")
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        user_id = user_id[0]  # Extraer el ID del resultado
        cursor.execute("INSERT INTO movimientos (id_partida, jugador, movimiento) VALUES (%s, %s, %s)", (id_partida, user_id, movimiento))
        conexion.commit()  # Confirma los cambios en la base de datos
        #logger.info(f"[envio] Movimiento insertado: {movimiento} para usuario {usuario} en partida {id_partida}")
        # Obtener el ID del movimiento insertado    
        id_movimiento = cursor.lastrowid
        #logger.info(f"[envio] ID del movimiento insertado: {id_movimiento}")
        return {"id_movimiento": id_movimiento}
    except Error as e:
        print(f"[envio] Error al conectar a la BD: {e}")
        #logger.error(f"[envio] Error al conectar a la BD: {e}")
        raise HTTPException(status_code=500, detail="Error de servidor")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

@app.get("/lectura") # Lee un movimiento pendiente de la base de datos
def lectura(usuario: str = Query(...), id_partida: int = Query(...)):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        # Obtener solo ID usuario por nombre
        cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", (usuario,))
        user_id = cursor.fetchone()
        if user_id is None:
            #logger.error(f"[lectura] Usuario no encontrado: {usuario}")
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        user_id = user_id[0]  # Extraer el ID del resultado
        cursor.execute("SELECT id FROM partidas WHERE id = %s", (id_partida,))
        partida = cursor.fetchone()
        if partida is None:
            #logger.error(f"[lectura] Partida no encontrada: {id_partida}")
            raise HTTPException(status_code=404, detail="Partida no encontrada")        
        id_partida = partida[0]  # Extraer el ID del resultado
        #logger.info(f"[lectura] ID de partida obtenido: {id_partida}")
        cursor.execute("SELECT id, movimiento FROM movimientos WHERE id_partida = %s AND recibido = 0 AND jugador != %s ORDER BY id ASC LIMIT 1", (id_partida, user_id))
        mov = cursor.fetchone()
        #logger.info(f"[lectura] Movimiento obtenido: {mov}")    
        if mov is None:
            return {"mensaje": "No hay movimientos para leer."}
        id_movimiento, movimiento = mov
        return {"id_movimiento": id_movimiento, "movimiento": movimiento}
    except Error as e:
        print(f"[lectura] Error al conectar a la BD: {e}")
        #logger.error(f"[lectura] Error al conectar a la BD: {e}")
        raise HTTPException(status_code=500, detail="Error de servidor")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

@app.get("/ack") # Marca un movimiento como recibido
def ack(id_movimiento: int = Query(...)):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("UPDATE movimientos SET recibido = 1 WHERE id = %s", (id_movimiento,))
        conexion.commit()  # Confirma los cambios en la base de datos
        #logger.info(f"[ack] Movimiento {id_movimiento} marcado como recibido")
        if cursor.rowcount == 0:
            #logger.error(f"[ack] Movimiento no encontrado: {id_movimiento}")
            raise HTTPException(status_code=404, detail="Movimiento no encontrado")
        return {"movimiento_confirmado": id_movimiento}
    except Error as e:
        print(f"[ack] Error al conectar a la BD: {e}")
        #logger.error(f"[ack] Error al conectar a la BD: {e}")
        raise HTTPException(status_code=500, detail="Error de servidor")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

@app.get("/check")  # Verifica si un movimiento ha sido recibido
def check(id_movimiento: int = Query(...)):
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT recibido FROM movimientos WHERE id = %s", (id_movimiento,))
        resultado = cursor.fetchone()
        if resultado is None:
            #logger.error(f"[check] Movimiento no encontrado: {id_movimiento}")
            raise HTTPException(status_code=404, detail="Movimiento no encontrado")
        
        recibido = resultado[0]
        #logger.info(f"[check] Movimiento {id_movimiento} recibido: {recibido}")
        # Devuelve un mensaje dependiendo del estado de recibido
        return {"mensaje": "Recibido" if recibido == 1 else "No recibido"}

    except Error as e:
        print(f"[check] Error al conectar a la BD: {e}")
        #logger.error(f"[check] Error al conectar a la BD: {e}")
        raise HTTPException(status_code=500, detail="Error de servidor")

    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()


# ==== AVATARES PREDEFINIDOS ====
# La foto de perfil es solamente un índice que apunta a una imagen de la carpeta
# "static/perfiles". Las primeras 15 imágenes (índices 0..14) son gratis; del índice
# 15 en adelante son de pago (microtransacción con Mercado Pago).
RUTA_PERFILES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "perfiles")
EXT_PERMITIDAS = (".png", ".jpg", ".jpeg", ".gif", ".webp")
AVATARES_PAGO_DESDE = 15  # índice 0-based: 0..14 gratis, >=15 de pago
PRECIO_AVATAR = float(os.environ.get("AVATAR_PRECIO", "2000"))  # precio en la moneda de la cuenta MP


def _lista_avatares():
    """Devuelve la lista ORDENADA de nombres de archivo en static/perfiles."""
    if not os.path.isdir(RUTA_PERFILES):
        return []
    archivos = [f for f in os.listdir(RUTA_PERFILES) if f.lower().endswith(EXT_PERMITIDAS)]
    # Orden natural: separa dígitos y texto para mantener un orden estable y predecible.
    archivos.sort(key=lambda s: [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)])
    return archivos


def _total_avatares():
    return len(_lista_avatares())


def _avatar_pagado(indice):
    archivos = _lista_avatares()
    if indice < 0 or indice >= len(archivos):
        return False
    return "premium" in archivos[indice].lower()


def _crear_tabla_compras(conexion):
    cursor = conexion.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS avatares_comprados (
            id INT AUTO_INCREMENT PRIMARY KEY,
            usuario_id INT NOT NULL,
            avatar_index INT NOT NULL,
            pagado TINYINT NOT NULL DEFAULT 1,
            fecha DATETIME DEFAULT NULL,
            UNIQUE KEY uq_user_avatar (usuario_id, avatar_index)
        )
        """
    )
    conexion.commit()
    cursor.close()


def _avatar_comprado(conexion, usuario_id, indice):
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT 1 FROM avatares_comprados WHERE usuario_id = %s AND avatar_index = %s LIMIT 1",
        (usuario_id, indice),
    )
    ok = cursor.fetchone() is not None
    cursor.close()
    return ok


def _marcar_avatar_comprado(conexion, usuario_id, indice):
    cursor = conexion.cursor()
    cursor.execute(
        "INSERT IGNORE INTO avatares_comprados (usuario_id, avatar_index, pagado, fecha) VALUES (%s, %s, 1, %s)",
        (usuario_id, indice, datetime.utcnow() - timedelta(hours=3)),
    )
    conexion.commit()
    cursor.close()


def _fila_a_dict(cursor, fila):
    """Convierte una fila de mysql en un dict usando los nombres de columna."""
    if fila is None:
        return None
    columnas = [d[0] for d in cursor.description]
    return dict(zip(columnas, fila))


def _columna_password(conexion):
    """Detecta dinámicamente el nombre de la columna que guarda el hash de la contraseña."""
    cursor = conexion.cursor()
    cursor.execute("SHOW COLUMNS FROM usuarios")
    columnas = [r[0] for r in cursor.fetchall()]
    conocidas = {"id", "usuario", "exp", "estado", "ultima_actividad", "foto_perfil", "session_id"}
    for c in columnas:
        if c not in conocidas:
            cursor.close()
            return c
    cursor.close()
    return "contrasena"


@app.post("/page_register")  # Registra un nuevo usuario desde la página web
def page_register(datos: dict):
    usuario = (datos.get("usuario") or "").strip()
    contrasena = datos.get("contrasena") or ""
    foto = datos.get("foto_perfil")

    if not usuario or not contrasena:
        raise HTTPException(status_code=400, detail="Faltan usuario o contraseña")
    if len(usuario) > 30 or len(contrasena) > 80:
        raise HTTPException(status_code=400, detail="Usuario o contraseña demasiado largos")

    if foto is not None:
        try:
            foto = int(foto)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="foto_perfil debe ser un número entero")
        if foto < 0 or foto >= _total_avatares():
            raise HTTPException(status_code=400, detail="foto_perfil fuera de rango")
        if _avatar_pagado(foto):
            raise HTTPException(status_code=402, detail="Ese avatar es de pago, debes comprarlo primero")
    else:
        foto = 0

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", (usuario,))
        if cursor.fetchone():
            raise HTTPException(status_code=409, detail="El usuario ya existe")

        col_pw = _columna_password(conexion)
        hash_pw = generate_password_hash(contrasena)
        cursor.execute(
            f"INSERT INTO usuarios (usuario, {col_pw}, exp, foto_perfil) VALUES (%s, %s, 0, %s)",
            (usuario, hash_pw, foto),
        )
        conexion.commit()
        return {"status": "ok", "usuario": usuario, "exp": 0, "foto_perfil": foto}
    except HTTPException:
        raise
    except Error as e:
        logger.error(f"[page_register] Error al conectar a la BD: {e}")
        raise HTTPException(status_code=500, detail="Error de servidor")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()


@app.post("/page_login")  # Inicia sesión desde la página web y devuelve el perfil
def page_login(datos: dict):
    usuario = (datos.get("usuario") or "").strip()
    contrasena = datos.get("contrasena") or ""

    if not usuario or not contrasena:
        raise HTTPException(status_code=400, detail="Faltan usuario o contraseña")

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT * FROM usuarios WHERE usuario = %s", (usuario,))
        fila = _fila_a_dict(cursor, cursor.fetchone())
        if not fila:
            return {"status": "error", "mensaje": "Usuario no encontrado"}

        col_pw = _columna_password(conexion)
        if not check_password_hash(fila[col_pw], contrasena):
            return {"status": "error", "mensaje": "Contraseña incorrecta"}

        cursor.execute("UPDATE usuarios SET estado = 1 WHERE id = %s", (fila["id"],))
        conexion.commit()

        return {
            "status": "ok",
            "usuario": fila["usuario"],
            "exp": fila.get("exp", 0),
            "foto_perfil": fila.get("foto_perfil", 0) or 0,
        }
    except HTTPException:
        raise
    except Error as e:
        logger.error(f"[page_login] Error al conectar a la BD: {e}")
        raise HTTPException(status_code=500, detail="Error de servidor")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()


@app.get("/page_leaderboard")  # Devuelve la tabla de posiciones ordenada por experiencia
def page_leaderboard(limite: int = 50):
    limite = max(1, min(limite, 100))
    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute(
            "SELECT usuario, exp, foto_perfil FROM usuarios ORDER BY exp DESC LIMIT %s",
            (limite,),
        )
        filas = cursor.fetchall()
        posiciones = [
            {
                "posicion": i + 1,
                "usuario": f[0],
                "exp": f[1] or 0,
                "foto_perfil": (f[2] or 0),
            }
            for i, f in enumerate(filas)
        ]
        return {"status": "ok", "posiciones": posiciones}
    except Error as e:
        logger.error(f"[page_leaderboard] Error al conectar a la BD: {e}")
        raise HTTPException(status_code=500, detail="Error de servidor")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()


@app.post("/page_update_profile")  # Actualiza usuario, contraseña y foto de perfil
def page_update_profile(datos: dict):
    usuario = (datos.get("usuario") or "").strip()
    nuevo_usuario = (datos.get("nuevo_usuario") or "").strip()
    nueva_contrasena = datos.get("nueva_contrasena") or ""
    foto = datos.get("foto_perfil")

    if not usuario:
        raise HTTPException(status_code=400, detail="Falta el usuario actual")

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        cursor.execute("SELECT * FROM usuarios WHERE usuario = %s", (usuario,))
        fila = _fila_a_dict(cursor, cursor.fetchone())
        if not fila:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")

        col_pw = _columna_password(conexion)

        # Actualizar nombre de usuario
        if nuevo_usuario and nuevo_usuario != fila["usuario"]:
            if len(nuevo_usuario) > 30:
                raise HTTPException(status_code=400, detail="Usuario demasiado largo")
            cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", (nuevo_usuario,))
            if cursor.fetchone():
                raise HTTPException(status_code=409, detail="Ese nombre de usuario ya está en uso")
            cursor.execute("UPDATE usuarios SET usuario = %s WHERE id = %s", (nuevo_usuario, fila["id"]))
            usuario = nuevo_usuario

        # Actualizar contraseña
        if nueva_contrasena:
            if len(nueva_contrasena) > 80:
                raise HTTPException(status_code=400, detail="Contraseña demasiado larga")
            hash_pw = generate_password_hash(nueva_contrasena)
            cursor.execute(f"UPDATE usuarios SET {col_pw} = %s WHERE id = %s", (hash_pw, fila["id"]))

        # Actualizar foto de perfil (índice del arreglo de avatares)
        if foto is not None:
            try:
                foto = int(foto)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="foto_perfil debe ser un número entero")
            if foto < 0 or foto >= _total_avatares():
                raise HTTPException(status_code=400, detail="foto_perfil fuera de rango")
            # Los avatares de pago solo se pueden usar si fueron comprados.
            if _avatar_pagado(foto) and not _avatar_comprado(conexion, fila["id"], foto):
                raise HTTPException(status_code=402, detail="Ese avatar es de pago, debes comprarlo primero")
            cursor.execute("UPDATE usuarios SET foto_perfil = %s WHERE id = %s", (foto, fila["id"]))

        conexion.commit()

        # Devolver el perfil actualizado
        cursor.execute("SELECT exp, foto_perfil FROM usuarios WHERE id = %s", (fila["id"],))
        actual = cursor.fetchone()
        return {
            "status": "ok",
            "usuario": usuario,
            "exp": actual[0] or 0,
            "foto_perfil": actual[1] or 0,
        }
    except HTTPException:
        raise
    except Error as e:
        logger.error(f"[page_update_profile] Error al conectar a la BD: {e}")
        raise HTTPException(status_code=500, detail="Error de servidor")
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()


@app.get("/profilepicture")  # Sirve la imagen de perfil predefinida por índice (usado por el cliente GameMaker)
def profilepicture(usuario: str = Query(...), picture: int = Query(...)):
    archivos = _lista_avatares()
    if picture < 0 or picture >= len(archivos):
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    ruta = os.path.join(RUTA_PERFILES, archivos[picture])
    if not os.path.isfile(ruta):
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    return FileResponse(ruta)


@app.get("/Truco_Online/imagenes/{usuario:path}")  # Acepta "/<usuario>" o "/<usuario>.jpg" (usado por GameMaker / objProfileImage)
def imagen_perfil_usuario(usuario: str):
    if usuario.lower().endswith(".jpg"):
        usuario = usuario[:-4]
    idx = 0
    try:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        try:
            cursor.execute("SELECT foto_perfil FROM usuarios WHERE usuario = %s", (usuario,))
            r = cursor.fetchone()
            if r:
                try:
                    idx = int(r[0])
                except (TypeError, ValueError):
                    idx = 0
        finally:
            if conexion.is_connected():
                cursor.close()
                conexion.close()
    except Exception as e:
        logger.error(f"[imagen_perfil_usuario] Error al consultar DB para '{usuario}': {e}")
        idx = 0

    archivos = _lista_avatares()
    if not archivos:
        logger.error("[imagen_perfil_usuario] No hay avatares en RUTA_PERFILES=%s", RUTA_PERFILES)
        raise HTTPException(status_code=404, detail="Sin avatares configurados")
    if idx < 0 or idx >= len(archivos):
        idx = 0
    ruta = os.path.join(RUTA_PERFILES, archivos[idx])
    if not os.path.isfile(ruta):
        raise HTTPException(status_code=404, detail="Imagen no encontrada")
    return FileResponse(ruta, media_type="image/png", filename=archivos[idx])


@app.get("/page_avatars")  # Lista los avatares disponibles y si son de pago / ya comprados
def page_avatars(usuario: str = Query(None)):
    archivos = _lista_avatares()
    usuario_id = None
    comprados = set()
    if usuario:
        conexion = obtener_conexion()
        cursor = conexion.cursor()
        try:
            cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", (usuario,))
            r = cursor.fetchone()
            if r:
                usuario_id = r[0]
                _crear_tabla_compras(conexion)
                cursor.execute(
                    "SELECT avatar_index FROM avatares_comprados WHERE usuario_id = %s",
                    (usuario_id,),
                )
                comprados = {row[0] for row in cursor.fetchall()}
        finally:
            if conexion.is_connected():
                cursor.close()
                conexion.close()

    avatares = []
    for idx, nombre in enumerate(archivos):
        pagado = _avatar_pagado(idx)
        if pagado:
            owned = idx in comprados
        else:
            owned = True  # los gratis siempre están disponibles
        avatares.append({
            "index": idx,
            "url": "perfiles/" + nombre,
            "pagado": pagado,
            "owned": owned,
            "precio": PRECIO_AVATAR,
        })
    return {"status": "ok", "avatares": avatares, "pago_desde": AVATARES_PAGO_DESDE}


def _obtener_usuario_id(conexion, usuario):
    cursor = conexion.cursor()
    cursor.execute("SELECT id FROM usuarios WHERE usuario = %s", (usuario,))
    r = cursor.fetchone()
    cursor.close()
    return r[0] if r else None


# ==== Mercado Pago: configuración y helpers (credenciales SOLO por environment) ====
MP_WEBHOOK_SECRET = os.environ.get("MP_WEBHOOK_SECRET", "")
MP_CURRENCY = os.environ.get("MP_CURRENCY", "ARS")
MP_NOTIFICATION_URL = os.environ.get("MP_NOTIFICATION_URL", "")
MP_BACK_URL = os.environ.get("MP_BACK_URL", "/")
N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "")


def _mp_token():
    token = os.environ.get("MP_ACCESS_TOKEN")
    if not token:
        raise HTTPException(status_code=500, detail="Mercado Pago no está configurado (falta MP_ACCESS_TOKEN)")
    return token


def _mp_sdk():
    try:
        import mercadopago
    except ImportError:
        raise HTTPException(status_code=500, detail="Falta instalar la librería 'mercadopago'")
    return mercadopago.SDK(_mp_token())


def _crear_tabla_ordenes(conexion):
    cursor = conexion.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ordenes_mp (
            id VARCHAR(36) PRIMARY KEY,
            usuario_id INT NOT NULL,
            avatar_index INT NOT NULL,
            amount DECIMAL(10,2) NOT NULL,
            currency VARCHAR(8) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            mp_preference_id VARCHAR(64) DEFAULT NULL,
            mp_payment_id BIGINT DEFAULT NULL,
            created_at DATETIME DEFAULT NULL,
            paid_at DATETIME DEFAULT NULL,
            UNIQUE KEY uq_mp_payment (mp_payment_id)
        )
        """
    )
    conexion.commit()
    cursor.close()


def _obtener_orden(conexion, order_id):
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT id, usuario_id, avatar_index, amount, currency, status FROM ordenes_mp WHERE id = %s",
        (order_id,),
    )
    r = cursor.fetchone()
    cursor.close()
    if not r:
        return None
    return {
        "id": r[0], "usuario_id": r[1], "avatar_index": r[2],
        "amount": float(r[3]), "currency": r[4], "status": r[5],
    }


def _confirmar_orden(conexion, order_id, payment_id, usuario_id, indice, ahora):
    """Marca la orden como pagada de forma idempotente y habilita el avatar.

    Devuelve True sólo si esta llamada fue la que confirmó la orden; las
    llamadas repetidas (webhook duplicado o concurrente) devuelven False y no
    vuelven a desbloquear el avatar."""
    cursor = conexion.cursor()
    try:
        cursor.execute(
            "UPDATE ordenes_mp SET status = 'paid', mp_payment_id = %s, paid_at = %s "
            "WHERE id = %s AND status = 'pending'",
            (payment_id, ahora, order_id),
        )
        if cursor.rowcount == 0:
            return False
        conexion.commit()
    finally:
        cursor.close()
    _marcar_avatar_comprado(conexion, usuario_id, indice)
    return True


def _validar_firma_mp(x_signature, x_request_id, data_id):
    """Valida la firma x-signature de Mercado Pago con MP_WEBHOOK_SECRET.

    Plantilla oficial: id:{data_id};request-id:{x_request_id};ts:{ts};"""
    if not MP_WEBHOOK_SECRET:
        logger.warning("[webhook] MP_WEBHOOK_SECRET no configurado: se omite la validación de firma")
        return True
    if not x_signature:
        return False
    partes = {}
    for par in x_signature.split(","):
        if "=" in par:
            k, v = par.split("=", 1)
            partes[k] = v
    ts = partes.get("ts")
    # MP puede enviar la firma en "v1" (formato actual) o "signature" (legacy)
    firma = partes.get("v1") or partes.get("signature", "")
    if firma.startswith("hmac_sha256="):
        firma = firma[len("hmac_sha256="):]
    logger.info(f"[webhook] x-signature={x_signature} x-request-id={x_request_id} data_id={data_id}")
    if not ts or not data_id or not x_request_id:
        return False
    template = f"id:{data_id};request-id:{x_request_id};ts:{ts};"
    calculada = hmac.new(MP_WEBHOOK_SECRET.encode(), template.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(calculada, firma)


def _notificar_n8n(payload):
    """Avisa a n8n (webhook) que hubo una compra confirmada, para disparar el reporte.
    Se ejecuta en segundo plano para no demorar la respuesta a Mercado Pago."""
    if not N8N_WEBHOOK_URL:
        return
    try:
        requests.post(N8N_WEBHOOK_URL, json=payload, timeout=5)
    except Exception as e:
        logger.warning(f"[n8n] No se pudo notificar la compra a n8n: {e}")


def _crear_tabla_donaciones(conexion):
    cursor = conexion.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS donaciones_mp (
            id VARCHAR(36) PRIMARY KEY,
            usuario VARCHAR(30) DEFAULT NULL,
            amount DECIMAL(10,2) NOT NULL,
            currency VARCHAR(8) NOT NULL,
            status VARCHAR(16) NOT NULL DEFAULT 'pending',
            mp_preference_id VARCHAR(64) DEFAULT NULL,
            mp_payment_id BIGINT DEFAULT NULL,
            created_at DATETIME DEFAULT NULL,
            paid_at DATETIME DEFAULT NULL,
            UNIQUE KEY uq_don_mp_payment (mp_payment_id)
        )
        """
    )
    conexion.commit()
    cursor.close()


def _obtener_donacion(conexion, order_id):
    cursor = conexion.cursor()
    cursor.execute(
        "SELECT id, usuario, amount, currency, status FROM donaciones_mp WHERE id = %s",
        (order_id,),
    )
    r = cursor.fetchone()
    cursor.close()
    if not r:
        return None
    return {"id": r[0], "usuario": r[1], "amount": float(r[2]), "currency": r[3], "status": r[4]}


def _confirmar_donacion(conexion, order_id, payment_id, ahora):
    """Marca la donación como pagada de forma idempotente (evita dobles inserts)."""
    cursor = conexion.cursor()
    try:
        cursor.execute(
            "UPDATE donaciones_mp SET status = 'paid', mp_payment_id = %s, paid_at = %s "
            "WHERE id = %s AND status = 'pending'",
            (payment_id, ahora, order_id),
        )
        confirmado = cursor.rowcount > 0
        conexion.commit()
    finally:
        cursor.close()
    return confirmado


@app.post("/page_comprar_avatar")  # Crea una orden y una preferencia de pago en Mercado Pago
def page_comprar_avatar(datos: dict):
    usuario = (datos.get("usuario") or "").strip()
    try:
        indice = int(datos.get("avatar_index"))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="avatar_index inválido")

    archivos = _lista_avatares()
    if indice < 0 or indice >= len(archivos):
        raise HTTPException(status_code=400, detail="avatar_index fuera de rango")
    if not _avatar_pagado(indice):
        raise HTTPException(status_code=400, detail="Ese avatar es gratis")

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        usuario_id = _obtener_usuario_id(conexion, usuario)
        if not usuario_id:
            raise HTTPException(status_code=404, detail="Usuario no encontrado")
        _crear_tabla_compras(conexion)
        _crear_tabla_ordenes(conexion)
        if _avatar_comprado(conexion, usuario_id, indice):
            return {"status": "ok", "ya_comprado": True, "order_id": None, "init_point": None}
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

    sdk = _mp_sdk()
    # El precio SIEMPRE lo define el servidor; el cliente nunca lo envía.
    amount = PRECIO_AVATAR
    order_id = str(uuid.uuid4())
    ahora = datetime.utcnow() - timedelta(hours=3)
    preference_data = {
        "items": [
            {
                "title": f"Avatar Truco Online #{indice}",
                "quantity": 1,
                "unit_price": amount,
                "currency_id": MP_CURRENCY,
            }
        ],
        "external_reference": order_id,  # identificador impredecible de nuestra orden
        "metadata": {"usuario": usuario, "avatar_index": indice},
        "notification_url": MP_NOTIFICATION_URL,
        "back_urls": {
            "success": MP_BACK_URL,
            "failure": MP_BACK_URL,
            "pending": MP_BACK_URL,
        },
        "auto_return": "approved",
    }
    preference = sdk.preference().create(preference_data)
    if preference.get("status") not in (200, 201) or "response" not in preference:
        logger.error(f"[page_comprar_avatar] Error creando preferencia MP: {preference}")
        raise HTTPException(status_code=500, detail="No se pudo crear el pago en Mercado Pago")

    init_point = preference["response"].get("init_point")
    preference_id = preference["response"].get("id")

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        _crear_tabla_ordenes(conexion)
        cursor.execute(
            """
            INSERT INTO ordenes_mp
                (id, usuario_id, avatar_index, amount, currency, status, mp_preference_id, created_at)
            VALUES (%s, %s, %s, %s, %s, 'pending', %s, %s)
            """,
            (order_id, usuario_id, indice, amount, MP_CURRENCY, preference_id, ahora),
        )
        conexion.commit()
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

    logger.info(f"[page_comprar_avatar] Orden creada: {order_id} pref={preference_id} usuario={usuario}")
    return {
        "status": "ok",
        "order_id": order_id,
        "init_point": init_point,
        "preference_id": preference_id,
    }


@app.post("/page_donar")  # Crea una preferencia de donación en Mercado Pago y registra la orden
def page_donar(datos: dict = None):
    datos = datos or {}
    usuario = (datos.get("usuario") or "").strip() or None
    try:
        monto = float(datos.get("monto") or os.environ.get("DONACION_MONTO", "100"))
    except (TypeError, ValueError):
        monto = 100.0
    if monto <= 0:
        monto = 100.0

    sdk = _mp_sdk()
    order_id = str(uuid.uuid4())
    ahora = datetime.utcnow() - timedelta(hours=3)
    preference_data = {
        "items": [
            {
                "title": "Donación Truco Online",
                "quantity": 1,
                "unit_price": monto,
                "currency_id": MP_CURRENCY,
            }
        ],
        "external_reference": order_id,
        "metadata": {"usuario": usuario} if usuario else {},
        "notification_url": MP_NOTIFICATION_URL,
        "back_urls": {
            "success": MP_BACK_URL,
            "failure": MP_BACK_URL,
            "pending": MP_BACK_URL,
        },
        "auto_return": "approved",
    }
    preference = sdk.preference().create(preference_data)
    if preference.get("status") not in (200, 201) or "response" not in preference:
        logger.error(f"[page_donar] Error creando preferencia MP: {preference}")
        raise HTTPException(status_code=500, detail="No se pudo crear la donación en Mercado Pago")

    init_point = preference["response"].get("init_point")
    preference_id = preference["response"].get("id")

    conexion = obtener_conexion()
    cursor = conexion.cursor()
    try:
        _crear_tabla_donaciones(conexion)
        cursor.execute(
            """
            INSERT INTO donaciones_mp
                (id, usuario, amount, currency, status, mp_preference_id, created_at)
            VALUES (%s, %s, %s, %s, 'pending', %s, %s)
            """,
            (order_id, usuario, monto, MP_CURRENCY, preference_id, ahora),
        )
        conexion.commit()
    finally:
        if conexion.is_connected():
            cursor.close()
            conexion.close()

    logger.info(f"[page_donar] Donación creada: {order_id} usuario={usuario} monto={monto}")
    return {
        "status": "ok",
        "order_id": order_id,
        "init_point": init_point,
        "preference_id": preference_id,
    }


@app.post("/page_mp_webhook")
@app.get("/page_mp_webhook")
async def page_mp_webhook(request: Request):
    # Mercado Pago puede enviar GET (verificación/handshake) o POST (notificación).
    x_signature = request.headers.get("x-signature", "")
    x_request_id = request.headers.get("x-request-id", "")

    # El body puede venir como JSON o como query params (webhook legacy).
    datos = {}
    try:
        body = await request.body()
        if body:
            datos = await request.json()
    except Exception:
        datos = {}
    if not datos:
        datos = dict(request.query_params)

    tipo = datos.get("type") or datos.get("topic")
    data = datos.get("data")
    # data.id puede venir en query params (?data.id=) o en el body (data.id)
    data_id = datos.get("data.id")
    if not data_id and isinstance(data, dict):
        data_id = data.get("id")

    if request.method == "GET":
        return {"status": "ok"}

    if tipo not in ("payment",) or not data_id:
        logger.info(f"[webhook] Notificación ignorada tipo={tipo}")
        return {"status": "ignored"}

    # 1) Validar la firma del webhook (autoridad de la notificación).
    if not _validar_firma_mp(x_signature, x_request_id, str(data_id)):
        logger.warning(f"[webhook] Firma inválida para payment {data_id}")
        raise HTTPException(status_code=401, detail="Firma inválida")

    # 2) La notificación NO es prueba de pago: consultamos el Payment a la API de MP.
    sdk = _mp_sdk()
    payment = sdk.payment().get(data_id)
    info = payment.get("response", {})
    logger.info(f"[webhook] Payment {data_id} status={info.get('status')}")

    if info.get("status") != "approved":
        return {"status": "pending"}

    external_reference = info.get("external_reference")
    transaction_amount = info.get("transaction_amount")
    currency_id = info.get("currency_id")

    conexion = obtener_conexion()
    try:
        _crear_tabla_ordenes(conexion)
        _crear_tabla_donaciones(conexion)

        orden = _obtener_orden(conexion, external_reference) if external_reference else None
        donacion = None
        if not orden and external_reference:
            donacion = _obtener_donacion(conexion, external_reference)

        if not orden and not donacion:
            logger.warning(f"[webhook] Referencia no encontrada: {external_reference}")
            return {"status": "referencia_no_encontrada"}

        # 3) Validar monto y moneda contra lo registrado (servidor es autoridad).
        if abs(float((orden or donacion)["amount"]) - float(transaction_amount or 0)) > 0.01:
            logger.error(f"[webhook] Monto no coincide ref={external_reference} mp={transaction_amount}")
            return {"status": "monto_invalido"}
        if (orden or donacion)["currency"] != currency_id:
            logger.error(f"[webhook] Moneda no coincide ref={external_reference} mp={currency_id}")
            return {"status": "moneda_invalida"}

        ahora = datetime.utcnow() - timedelta(hours=3)
        if orden:
            if orden["status"] == "paid":
                return {"status": "ok"}  # ya procesada: idempotente
            confirmado = _confirmar_orden(
                conexion, orden["id"], int(data_id), orden["usuario_id"], orden["avatar_index"], ahora
            )
            if confirmado:
                logger.info(
                    f"[webhook] Orden {orden['id']} pagada y avatar {orden['avatar_index']} habilitado"
                )
                threading.Thread(
                    target=_notificar_n8n,
                    args=({"tipo": "avatar", "usuario_id": orden["usuario_id"],
                           "avatar_index": orden["avatar_index"], "monto": orden["amount"]},),
                    daemon=True,
                ).start()
        else:
            if donacion["status"] == "paid":
                return {"status": "ok"}  # ya procesada: idempotente
            confirmado = _confirmar_donacion(conexion, donacion["id"], int(data_id), ahora)
            if confirmado:
                logger.info(f"[webhook] Donación {donacion['id']} registrada como pagada (usuario={donacion['usuario']})")
                threading.Thread(
                    target=_notificar_n8n,
                    args=({"tipo": "donacion", "usuario": donacion["usuario"], "monto": donacion["amount"]},),
                    daemon=True,
                ).start()
    finally:
        if conexion.is_connected():
            conexion.close()
    return {"status": "ok"}


@app.get("/page_order_status")  # Consulta el estado de una orden (usado por el cliente para polling)
def page_order_status(order_id: str = Query(...), usuario: str = Query(None)):
    conexion = obtener_conexion()
    try:
        orden = _obtener_orden(conexion, order_id)
        if not orden:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        return {"status": orden["status"], "avatar_index": orden["avatar_index"]}
    finally:
        if conexion.is_connected():
            conexion.close()


# ==== Servir el juego (carpeta "game", hermana de "static") bajo /game ====
# Debe registrarse ANTES del mount "/" para que las rutas /game/* tengan
# precedencia sobre el directorio estático general.
# Se usan rutas absolutas basadas en la ubicación de este archivo para no
# depender del directorio de trabajo (WorkingDirectory) del service.
_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/game", StaticFiles(directory=os.path.join(_BASE_DIR, "game"), html=True), name="game")

# ==== Servir la web estática (index.html, styles.css, js, perfiles) ====
# Con root_path="/api", la API queda en /api/* y el sitio es accesible tanto en
# "/" como en "/api/". Los assets relativos (perfiles/..., asset1.png, etc.) resuelven bien.
app.mount("/", StaticFiles(directory=os.path.join(_BASE_DIR, "static"), html=True), name="static")

