// ==== Configuración ====
const API = "/api";

// Avatares de respaldo (mismo orden que el backend: static/perfiles 1.png..25.png).
// Del índice 15 en adelante son de pago (api.py: AVATARES_PAGO_DESDE = 15).
const AVATARS_FALLBACK = Array.from({ length: 25 }, (_, i) => ({
  index: i,
  url: "perfiles/" + (i + 1) + ".png",
  pagado: ("perfiles/" + (i + 1) + ".png").toLowerCase().includes("premium"),
  owned: i < 15,
  precio: 2000,
}));

let AVATARS = AVATARS_FALLBACK.slice();
let sesion = null; // { usuario, exp, foto_perfil }
let selectedAvatarRegister = 0;
let selectedAvatarProfile = 0;

const avatarUrl = (idx) => {
  const a = AVATARS.find((x) => x.index === Number(idx));
  return a ? a.url : "perfiles/profile0.png";
};

// ==== Estado de sesión ====
function cargarSesion() {
  try {
    const raw = localStorage.getItem("truco_sesion");
    sesion = raw ? JSON.parse(raw) : null;
  } catch {
    sesion = null;
  }
}

function guardarSesion() {
  if (sesion) localStorage.setItem("truco_sesion", JSON.stringify(sesion));
  else localStorage.removeItem("truco_sesion");
}

// ==== Helpers de UI ====
const $ = (id) => document.getElementById(id);

function mostrarMensaje(el, texto, esError = true) {
  el.textContent = texto;
  el.hidden = false;
  el.style.color = esError ? "#ff5555" : "#55ff77";
}

function ocultarMensaje(el) {
  el.hidden = true;
  el.textContent = "";
}

async function apiFetch(ruta, opciones = {}) {
  const res = await fetch(API + ruta, {
    headers: { "Content-Type": "application/json" },
    ...opciones,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    const msg = (data && (data.detail || data.mensaje)) || "Error de red";
    throw new Error(msg);
  }
  return data;
}

// ==== Avatares ====
async function cargarAvatares() {
  try {
    const params = sesion ? "?usuario=" + encodeURIComponent(sesion.usuario) : "";
    const data = await apiFetch("/page_avatars" + params);
    if (data && Array.isArray(data.avatares) && data.avatares.length) {
      AVATARS = data.avatares;
      return;
    }
  } catch (e) {
    console.warn("No se pudo cargar avatares desde el backend, usando respaldo local.", e);
  }
  AVATARS = AVATARS_FALLBACK.slice();
}

function puedeUsar(a) {
  return !a.pagado || a.owned;
}

// ==== Navegación por secciones ====
function mostrarSeccion(nombre) {
  if (nombre === "jugar") {
    window.location.href = "/api/game/";
    return;
  }
  ["jugar", "tienda", "contacto", "perfil"].forEach((s) => {
    const el = $("seccion-" + s);
    if (el) el.hidden = s !== nombre;
  });
  document.querySelectorAll(".nav-link").forEach((l) => {
    l.classList.toggle("active", l.dataset.seccion === nombre);
  });
  if (nombre === "tienda") cargarTienda();
}

// ==== Render principal ====
function render() {
  const navUser = $("nav-user");
  const navLinks = $("nav-links");
  const authView = $("auth-view");
  const dashboard = $("dashboard");

  if (sesion) {
    navLinks.hidden = false;
    navUser.innerHTML = `
      <img class="nav-avatar" src="${avatarUrl(sesion.foto_perfil)}" alt="avatar" />
      <button class="nav-user-toggle" id="nav-toggle" type="button">
        <span class="nav-username">${sesion.usuario}</span>
        <span class="nav-caret">&#9662;</span>
      </button>
      <div class="nav-dropdown" id="nav-dropdown" hidden>
        <a class="nav-dropdown-item" href="#" data-seccion="jugar">Jugar</a>
        <a class="nav-dropdown-item" href="#" data-seccion="tienda">Tienda</a>
        <a class="nav-dropdown-item" href="#" data-seccion="contacto">Contacto</a>
        <a class="nav-dropdown-item" href="#" data-seccion="perfil">Mi Perfil</a>
        <a class="nav-dropdown-item" href="#" id="logout-btn">Cerrar sesión</a>
      </div>
    `;
    $("nav-toggle").addEventListener("click", (e) => {
      e.stopPropagation();
      const dd = $("nav-dropdown");
      dd.hidden = !dd.hidden;
    });
    document.querySelectorAll("#nav-dropdown .nav-dropdown-item[data-seccion]").forEach((item) => {
      item.addEventListener("click", (e) => {
        e.preventDefault();
        const sec = item.dataset.seccion;
        $("nav-dropdown").hidden = true;
        mostrarSeccion(sec);
      });
    });
    $("logout-btn").addEventListener("click", (e) => {
      e.preventDefault();
      sesion = null;
      guardarSesion();
      render();
    });
    document.addEventListener("click", (e) => {
      const dd = $("nav-dropdown");
      if (dd && !dd.hidden && !navUser.contains(e.target)) dd.hidden = true;
    });

    authView.hidden = true;
    dashboard.hidden = false;
    mostrarSeccion("perfil");

    $("profile-avatar").src = avatarUrl(sesion.foto_perfil);
    $("profile-name").textContent = sesion.usuario;
    $("profile-exp").textContent = "EXP: " + (sesion.exp || 0);

    cargarLeaderboard();
  } else {
    navLinks.hidden = true;
    navUser.innerHTML = "";
    authView.hidden = false;
    dashboard.hidden = true;
    construirAvatarGrid($("register-avatars"), "register", selectedAvatarRegister);
  }
}

// ==== Grilla de avatares ====
function construirAvatarGrid(contenedor, tipo, seleccionado) {
  contenedor.innerHTML = "";
  AVATARS.forEach((a) => {
    const cell = document.createElement("div");
    cell.className = "avatar-cell";

    const img = document.createElement("img");
    img.src = a.url;
    img.alt = "avatar " + a.index;
    if (a.index === seleccionado) img.classList.add("selected");
    if (a.pagado && !a.owned) img.classList.add("locked");

    if (a.pagado && !a.owned) {
      const lock = document.createElement("span");
      lock.className = "avatar-lock";
      lock.textContent = "$";
      cell.appendChild(lock);

      img.addEventListener("click", () => {
        if (tipo === "register") {
          mostrarMensaje($("register-msg"), "Regístrate primero y luego podrás comprar este avatar");
        } else {
          iniciarCompra(a.index);
        }
      });
    } else {
      img.addEventListener("click", () => {
        if (tipo === "register") selectedAvatarRegister = a.index;
        else selectedAvatarProfile = a.index;
        construirAvatarGrid(contenedor, tipo, a.index);
      });
    }

    cell.appendChild(img);
    contenedor.appendChild(cell);
  });
}

// ==== Modo vista / edición de perfil ====
function mostrarModoPerfil(editando) {
  $("profile-view").hidden = editando;
  $("profile-edit").hidden = !editando;
  ocultarMensaje($("profile-msg"));
}

function entrarEdicionPerfil() {
  mostrarModoPerfil(true);
  $("edit-usuario").value = sesion.usuario;
  $("edit-contrasena").value = "";
  selectedAvatarProfile = sesion.foto_perfil || 0;
  construirAvatarGrid($("profile-avatars"), "profile", selectedAvatarProfile);
}

// ==== Compra con Mercado Pago ====
async function iniciarCompra(indice) {
  ocultarMensaje($("profile-msg"));
  ocultarMensaje($("tienda-msg"));
  try {
    const data = await apiFetch("/page_comprar_avatar", {
      method: "POST",
      body: JSON.stringify({ usuario: sesion.usuario, avatar_index: indice }),
    });
    if (data.ya_comprado) {
      await recargarYseleccionar(indice);
      mostrarMensaje($("tienda-msg"), "Avatar ya comprado", false);
      return;
    }
    if (!data.init_point) {
      mostrarMensaje($("tienda-msg"), "No se pudo iniciar el pago");
      return;
    }
    mostrarMensaje($("tienda-msg"), "Abriendo Mercado Pago... completá el pago y volvé.", false);
    window.open(data.init_point, "_blank");
    iniciarPollingCompra(indice, data.order_id);
  } catch (err) {
    mostrarMensaje($("tienda-msg"), err.message);
  }
}

// Consulta periódicamente el estado de la orden en el servidor hasta que el
// webhook de Mercado Pago confirme el pago (el cliente nunca decide el estado).
function iniciarPollingCompra(indice, orderId) {
  let intentos = 0;
  const maxIntentos = 90; // ~3 minutos
  const tick = async () => {
    intentos++;
    try {
      const data = await apiFetch(
        "/page_order_status?order_id=" + encodeURIComponent(orderId) +
        "&usuario=" + encodeURIComponent(sesion.usuario)
      );
      if (data.status === "paid") {
        await recargarYseleccionar(indice);
        mostrarMensaje($("tienda-msg"), "¡Compra confirmada! Avatar desbloqueado.", false);
        cargarTienda();
        return;
      }
    } catch (e) {
      // se reintenta; el webhook puede tardar en llegar
    }
    if (intentos < maxIntentos) {
      setTimeout(tick, 2000);
    } else {
      mostrarMensaje(
        $("tienda-msg"),
        "No se pudo confirmar la compra automáticamente. Recargá la tienda en unos minutos.",
        true
      );
    }
  };
  setTimeout(tick, 2500);
}

async function recargarYseleccionar(indice) {
  await cargarAvatares();
  selectedAvatarProfile = indice;
  mostrarModoPerfil(true);
  construirAvatarGrid($("profile-avatars"), "profile", indice);
}

// ==== Donaciones ====
async function donar(monto) {
  ocultarMensaje($("tienda-msg"));
  try {
    const data = await apiFetch("/page_donar", {
      method: "POST",
      body: JSON.stringify({ monto, usuario: sesion ? sesion.usuario : null }),
    });
    if (!data.init_point) {
      mostrarMensaje($("tienda-msg"), "No se pudo iniciar la donación");
      return;
    }
    mostrarMensaje($("tienda-msg"), "Abriendo Mercado Pago...", false);
    window.open(data.init_point, "_blank");
  } catch (err) {
    mostrarMensaje($("tienda-msg"), err.message);
  }
}

// ==== Tienda ====
async function cargarTienda() {
  await cargarAvatares();

  const cont = $("store-avatars");
  cont.innerHTML = "";
  AVATARS.filter((a) => a.pagado).forEach((a) => {
    const item = document.createElement("div");
    item.className = "store-item";

    const img = document.createElement("img");
    img.src = a.url;
    img.alt = "avatar " + a.index;
    if (a.owned) img.classList.add("owned");

    const btn = document.createElement("button");
    btn.className = "btn-modern";
    if (a.owned) {
      btn.textContent = "Comprado";
      btn.disabled = true;
    } else {
      btn.textContent = "$" + (a.precio ?? 2000);
      btn.addEventListener("click", () => iniciarCompra(a.index));
    }

    item.appendChild(img);
    item.appendChild(btn);
    cont.appendChild(item);
  });

  const prem = [
    { nombre: "Mazo Dorado", desc: "Diseño premium de cartas" },
    { nombre: "Cartas Neón", desc: "Estilo neón brillante" },
    { nombre: "Fondo Animado", desc: "Fondo de mesa animado" },
    { nombre: "Cartas Clásicas", desc: "Piel de cartas clásica" },
  ];
  const premCont = $("store-premium");
  premCont.innerHTML = "";
  prem.forEach((p) => {
    const item = document.createElement("div");
    item.className = "store-item placeholder";
    item.innerHTML = `
      <div class="store-item-title">${p.nombre}</div>
      <div class="store-item-desc">${p.desc}</div>
      <span class="badge-prox">Próximamente</span>
    `;
    premCont.appendChild(item);
  });
}

// ==== Alternar login / registro ====
function mostrarLogin() {
  $("login-card").hidden = false;
  $("register-card").hidden = true;
  ocultarMensaje($("login-msg"));
}

function mostrarRegistro() {
  $("login-card").hidden = true;
  $("register-card").hidden = false;
  construirAvatarGrid($("register-avatars"), "register", selectedAvatarRegister);
  ocultarMensaje($("register-msg"));
}

// ==== Acciones ====
async function hacerLogin() {
  ocultarMensaje($("login-msg"));
  const usuario = $("login-usuario").value.trim();
  const contrasena = $("login-contrasena").value;
  if (!usuario || !contrasena) {
    mostrarMensaje($("login-msg"), "Completa usuario y contraseña");
    return;
  }
  try {
    const data = await apiFetch("/page_login", {
      method: "POST",
      body: JSON.stringify({ usuario, contrasena }),
    });
    if (data.status !== "ok") {
      mostrarMensaje($("login-msg"), data.mensaje || "No se pudo iniciar sesión");
      return;
    }
    sesion = { usuario: data.usuario, exp: data.exp, foto_perfil: data.foto_perfil };
    guardarSesion();
    await cargarAvatares();
    render();
  } catch (err) {
    mostrarMensaje($("login-msg"), err.message);
  }
}

async function hacerRegistro() {
  ocultarMensaje($("register-msg"));
  const usuario = $("register-usuario").value.trim();
  const contrasena = $("register-contrasena").value;
  if (!usuario || !contrasena) {
    mostrarMensaje($("register-msg"), "Completa usuario y contraseña");
    return;
  }
  if (!puedeUsar(AVATARS.find((a) => a.index === selectedAvatarRegister) || {})) {
    mostrarMensaje($("register-msg"), "El avatar seleccionado no está disponible");
    return;
  }
  try {
    const data = await apiFetch("/page_register", {
      method: "POST",
      body: JSON.stringify({ usuario, contrasena, foto_perfil: selectedAvatarRegister }),
    });
    if (data.status !== "ok") {
      mostrarMensaje($("register-msg"), data.detail || data.mensaje || "No se pudo registrar");
      return;
    }
    sesion = { usuario: data.usuario, exp: data.exp, foto_perfil: data.foto_perfil };
    guardarSesion();
    await cargarAvatares();
    render();
  } catch (err) {
    mostrarMensaje($("register-msg"), err.message);
  }
}

async function guardarPerfil() {
  ocultarMensaje($("profile-msg"));
  const nuevoUsuario = $("edit-usuario").value.trim();
  const nuevaContrasena = $("edit-contrasena").value;
  try {
    const data = await apiFetch("/page_update_profile", {
      method: "POST",
      body: JSON.stringify({
        usuario: sesion.usuario,
        nuevo_usuario: nuevoUsuario,
        nueva_contrasena: nuevaContrasena,
        foto_perfil: selectedAvatarProfile,
      }),
    });
    if (data.status !== "ok") {
      mostrarMensaje($("profile-msg"), data.detail || data.mensaje || "No se pudo guardar");
      return;
    }
    sesion = { usuario: data.usuario, exp: data.exp, foto_perfil: data.foto_perfil };
    guardarSesion();
    mostrarMensaje($("profile-msg"), "Perfil actualizado", false);
    render();
  } catch (err) {
    mostrarMensaje($("profile-msg"), err.message);
  }
}

async function cargarLeaderboard() {
  const msg = $("leaderboard-msg");
  ocultarMensaje(msg);
  try {
    const data = await apiFetch("/page_leaderboard?limite=10");
    const body = $("leaderboard-body");
    body.innerHTML = "";
    data.posiciones.forEach((p) => {
      const tr = document.createElement("tr");
      if (sesion && p.usuario === sesion.usuario) tr.classList.add("me");
      tr.innerHTML = `
        <td class="pos">${p.posicion}</td>
        <td><img class="row-avatar" src="${avatarUrl(p.foto_perfil)}" alt="" />${p.usuario}</td>
        <td>${p.exp}</td>
      `;
      body.appendChild(tr);
    });
  } catch (err) {
    mostrarMensaje(msg, err.message);
  }
}

// ==== Eventos ====
$("login-card").addEventListener("submit", (e) => { e.preventDefault(); hacerLogin(); });
$("register-card").addEventListener("submit", (e) => { e.preventDefault(); hacerRegistro(); });
$("save-profile-btn").addEventListener("click", guardarPerfil);
$("edit-profile-btn").addEventListener("click", entrarEdicionPerfil);
$("cancel-edit-btn").addEventListener("click", () => mostrarModoPerfil(false));
$("close-edit-btn").addEventListener("click", () => mostrarModoPerfil(false));
$("show-register").addEventListener("click", (e) => {
  e.preventDefault();
  mostrarRegistro();
});
$("show-login").addEventListener("click", (e) => {
  e.preventDefault();
  mostrarLogin();
});
document.querySelectorAll(".nav-link").forEach((link) => {
  link.addEventListener("click", (e) => {
    e.preventDefault();
    mostrarSeccion(link.dataset.seccion);
  });
});
document.querySelectorAll("[data-donar]").forEach((btn) => {
  btn.addEventListener("click", () => donar(parseFloat(btn.dataset.donar)));
});

// ==== Inicio ====
cargarSesion();
cargarAvatares()
  .then(render)
  .catch(() => render());
