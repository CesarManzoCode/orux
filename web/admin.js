/*
 * Capa 13 — panel admin con su propio espacio (modal), reparto MASIVO.
 *
 * Por qué existe: la primera queja real de uso. El panel viejo vivía en la
 * sidebar y era por-archivo: para 100 archivos había que picar archivo →
 * escudo → usuario → aplicar, cien veces. Inusable. Acá: árbol con
 * checkboxes, seleccionás archivos sueltos o CARPETAS enteras, elegís el
 * dueño UNA vez, "asignar a N". Manda un solo `admin_assign_many` y el
 * server difunde UN ownership (no 100).
 *
 * Script clásico (sin build, sin import): comparte el scope global con
 * app.js, que carga primero. Usa su estado/funciones tal cual (mismo
 * espejo, nada se duplica): `files`, `owners`, `usuariosLista`, `esAdmin`,
 * `ws`, `nombreDe`, `chipEl`, `_arbol`, `railAdminBtn`. Define el global
 * `renderAdmin()` que app.js invoca cuando cambia el ownership / admin_info
 * / se abre o cierra un archivo: si el modal está abierto, se redibuja con
 * los dueños frescos; si no, es no-op barato.
 *
 * Alcance mínimo y honesto: "carpeta" = todos los archivos bajo ella. El
 * ownership sigue siendo por archivo (ownership por prefijo es un cambio de
 * modelo deliberadamente diferido); seleccionar carpeta solo expande la
 * selección a paths concretos. El server revalida que sos admin: aunque un
 * no-admin forzara el mensaje, se ignora; y el modal ni se le abre.
 */
(function () {
  const modal = document.getElementById("adminmodal");
  const cerrarBtn = document.getElementById("amCerrar");
  const userSel = document.getElementById("amUser");
  const countEl = document.getElementById("amCount");
  const todosBtn = document.getElementById("amTodos");
  const nadaBtn = document.getElementById("amNada");
  const aplicarBtn = document.getElementById("amAplicar");
  const quitarBtn = document.getElementById("amQuitar");
  const treeEl = document.getElementById("amTree");
  const footEl = document.getElementById("amFoot");

  // Selección actual (paths de ARCHIVO). Carpetas no se guardan: se
  // expanden a sus archivos al togglear. Carpetas colapsadas: solo UI.
  const sel = new Set();
  const colapsadas = new Set();
  let abierto = false;

  // Todos los paths de archivo bajo un nodo del árbol de `_arbol`.
  function archivosDe(nodo) {
    let out = nodo.files.map((f) => f.path);
    for (const d of Object.keys(nodo.dirs)) {
      out = out.concat(archivosDe(nodo.dirs[d]));
    }
    return out;
  }

  function actualizarContador() {
    const n = sel.size;
    countEl.textContent =
      n + (n === 1 ? " seleccionado" : " seleccionados");
    aplicarBtn.disabled = n === 0 || !userSel.value;
    quitarBtn.disabled = n === 0;
    aplicarBtn.textContent = "asignar a " + n;
    quitarBtn.textContent = "quitar dueño a " + n;
  }

  // Reconstruye el <select> de usuarios conservando lo elegido.
  function pintarUsuarios() {
    const prev = userSel.value;
    userSel.innerHTML = "";
    const o0 = document.createElement("option");
    o0.value = "";
    o0.textContent = "— elegí un usuario —";
    userSel.appendChild(o0);
    for (const u of usuariosLista) {
      const o = document.createElement("option");
      o.value = u;
      o.textContent = u;
      userSel.appendChild(o);
    }
    if (prev && usuariosLista.includes(prev)) userSel.value = prev;
  }

  function pintarArbol() {
    treeEl.innerHTML = "";
    const paths = Object.keys(files);
    if (paths.length === 0) {
      const v = document.createElement("div");
      v.className = "amvacio";
      v.textContent = "no hay archivos en el workspace.";
      treeEl.appendChild(v);
      return;
    }
    const raiz = _arbol(paths);

    const pintar = (nodo, ruta, depth) => {
      for (const nombre of Object.keys(nodo.dirs).sort()) {
        const sub = nodo.dirs[nombre];
        const rutaDir = ruta ? ruta + "/" + nombre : nombre;
        const archivos = archivosDe(sub);
        const fila = document.createElement("div");
        fila.className = "amrow amdir";
        fila.style.paddingLeft = depth * 16 + 8 + "px";

        const chk = document.createElement("input");
        chk.type = "checkbox";
        // Tri-estado: marcado si TODOS sus archivos están; indeterminado
        // si algunos. Seleccionar/limpiar la carpeta = todos sus archivos.
        const dentro = archivos.filter((p) => sel.has(p)).length;
        chk.checked = dentro === archivos.length && archivos.length > 0;
        chk.indeterminate = dentro > 0 && dentro < archivos.length;
        chk.addEventListener("change", () => {
          if (chk.checked) archivos.forEach((p) => sel.add(p));
          else archivos.forEach((p) => sel.delete(p));
          pintarArbol();
          actualizarContador();
        });
        fila.appendChild(chk);

        const tw = document.createElement("span");
        tw.className = "amtw";
        const cerrada = colapsadas.has(rutaDir);
        tw.textContent = cerrada ? "▸" : "▾";
        const nm = document.createElement("span");
        nm.className = "amname amdname";
        nm.textContent = nombre + "/";
        const meta = document.createElement("span");
        meta.className = "ammeta";
        meta.textContent = archivos.length + "";
        const toggle = () => {
          if (colapsadas.has(rutaDir)) colapsadas.delete(rutaDir);
          else colapsadas.add(rutaDir);
          pintarArbol();
        };
        tw.addEventListener("click", toggle);
        nm.addEventListener("click", toggle);
        fila.appendChild(tw);
        fila.appendChild(nm);
        fila.appendChild(meta);
        treeEl.appendChild(fila);

        if (!cerrada) pintar(sub, rutaDir, depth + 1);
      }
      for (const f of nodo.files.slice().sort((a, b) =>
        a.nombre.localeCompare(b.nombre)
      )) {
        const fila = document.createElement("div");
        fila.className = "amrow amfile";
        fila.style.paddingLeft = depth * 16 + 26 + "px";

        const chk = document.createElement("input");
        chk.type = "checkbox";
        chk.checked = sel.has(f.path);
        chk.addEventListener("change", () => {
          if (chk.checked) sel.add(f.path);
          else sel.delete(f.path);
          // Repintar para refrescar el tri-estado de las carpetas padre.
          pintarArbol();
          actualizarContador();
        });
        fila.appendChild(chk);

        fila.appendChild(chipEl(f.path));
        const nm = document.createElement("span");
        nm.className = "amname";
        nm.textContent = f.nombre;
        fila.appendChild(nm);

        const due = owners[f.path];
        if (due) {
          const d = document.createElement("span");
          d.className = "amowner";
          d.textContent = "→ " + nombreDe(due);
          fila.appendChild(d);
        }
        // Clic en la fila (no en el checkbox) = togglear también.
        fila.addEventListener("click", (e) => {
          if (e.target === chk) return;
          chk.checked = !chk.checked;
          chk.dispatchEvent(new Event("change"));
        });
        treeEl.appendChild(fila);
      }
    };
    pintar(raiz, "", 0);
  }

  // Resumen honesto de lo que va a pasar (cuántos, a quién).
  function pintarPie() {
    const n = sel.size;
    if (n === 0) {
      footEl.textContent =
        "seleccioná archivos o carpetas; elegí un dueño; aplicá al lote.";
      return;
    }
    const u = userSel.value;
    footEl.textContent = u
      ? "“asignar” pondrá a «" + u + "» como dueño de " + n +
        " archivo(s). “quitar” los deja sin dueño."
      : n + " archivo(s) seleccionados — elegí un usuario para asignar, " +
        "o usá “quitar dueño”.";
  }

  function refrescar() {
    // No tiene sentido mantener seleccionados paths que ya no existen
    // (se borraron / se reinició el workspace por un clone).
    for (const p of [...sel]) if (!(p in files)) sel.delete(p);
    pintarUsuarios();
    pintarArbol();
    actualizarContador();
    pintarPie();
  }

  function abrir() {
    if (!esAdmin) return;
    abierto = true;
    modal.classList.add("on");
    refrescar();
  }
  function cerrar() {
    abierto = false;
    modal.classList.remove("on");
  }

  // GLOBAL: app.js la invoca cuando cambia ownership / admin_info /
  // archivo. Si el modal está abierto, lo redibuja con datos frescos; si
  // dejaste de ser admin, lo cierra. Cerrado = no-op barato.
  window.renderAdmin = function () {
    if (!esAdmin && abierto) cerrar();
    if (abierto) refrescar();
  };

  function aplicar(username) {
    if (sel.size === 0 || ws.readyState !== WebSocket.OPEN) return;
    ws.send(
      JSON.stringify({
        type: "admin_assign_many",
        paths: [...sel],
        username: username,
      })
    );
    // El server difunde el ownership nuevo → app.js → renderAdmin() lo
    // refresca. Limpiamos la selección para no reaplicar sin querer.
    sel.clear();
    actualizarContador();
    pintarPie();
  }

  cerrarBtn.addEventListener("click", cerrar);
  modal.addEventListener("click", (e) => {
    if (e.target === modal) cerrar();  // clic fuera de la tarjeta
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && abierto) cerrar();
  });
  todosBtn.addEventListener("click", () => {
    Object.keys(files).forEach((p) => sel.add(p));
    pintarArbol();
    actualizarContador();
    pintarPie();
  });
  nadaBtn.addEventListener("click", () => {
    sel.clear();
    pintarArbol();
    actualizarContador();
    pintarPie();
  });
  userSel.addEventListener("change", () => {
    actualizarContador();
    pintarPie();
  });
  aplicarBtn.addEventListener("click", () => aplicar(userSel.value));
  quitarBtn.addEventListener("click", () => aplicar(""));

  // El botón admin del rail (lo muestra/oculta app.js según esAdmin) abre
  // el modal. Es la única forma de entrar: no vive en la sidebar.
  if (railAdminBtn) railAdminBtn.addEventListener("click", abrir);
})();
