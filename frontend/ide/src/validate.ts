// Validación al borde del cliente: feedback INMEDIATO al usuario antes de
// que el WS rebote. El backend (paths.py / teams/store.py / identity/store.py)
// sigue siendo la verdad — esto es UX, no la compuerta de seguridad. Las
// reglas DEBEN coincidir con backend o el dev verá "pasa acá pero rebota
// allá". Si cambia una, cambian las dos.
//
// Cada función devuelve `null` si el valor es válido, o un código de error
// (string identificador) que el llamador traduce vía i18n. No devolvemos el
// mensaje literal porque la UI es bilingüe.

const PATH_MAX = 200;
const SEG_MAX = 80;
const PROFUNDIDAD_MAX = 16;
const PATH_PROHIBIDOS = /[<>:"|?*\\]/;
// Zero-width / bidi-override: suplantación visual. Mismos rangos que backend.
// eslint-disable-next-line no-misleading-character-class
const INVISIBLES = /[​-‏‪-‮⁦-⁩﻿]/;
const RESERVADOS_WIN = new Set([
  "CON", "PRN", "AUX", "NUL",
  "COM1", "COM2", "COM3", "COM4", "COM5", "COM6", "COM7", "COM8", "COM9",
  "LPT1", "LPT2", "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9",
]);

export type PathError =
  | "vacio" | "muy_largo" | "control" | "prohibido" | "invisible"
  | "absoluto" | "barra_invertida" | "segmento_vacio" | "punto" | "doble_punto"
  | "segmento_largo" | "profundidad" | "espacios_borde" | "reservado_win";

/** Devuelve `null` si el path es seguro, o un código de error si no. */
export function validarPath(path: string): PathError | null {
  if (typeof path !== "string" || !path) return "vacio";
  if (path.length > PATH_MAX) return "muy_largo";
  for (const c of path) {
    const co = c.charCodeAt(0);
    if (co < 0x20 || co === 0x7f) return "control";
    if (PATH_PROHIBIDOS.test(c)) return "prohibido";
    if (INVISIBLES.test(c)) return "invisible";
  }
  if (path.startsWith("/")) return "absoluto";
  if (
    path.length >= 2 && path[1] === ":" &&
    /[a-z]/i.test(path[0])
  ) return "absoluto";
  if (path.includes("\\")) return "barra_invertida";
  const segs = path.split("/");
  if (segs.length > PROFUNDIDAD_MAX) return "profundidad";
  for (const seg of segs) {
    if (seg === "") return "segmento_vacio";
    if (seg === ".") return "punto";
    if (seg === "..") return "doble_punto";
    if (seg.length > SEG_MAX) return "segmento_largo";
    if (seg !== seg.trim()) return "espacios_borde";
    const stem = seg.includes(".") ? seg.split(".")[0] : seg;
    if (RESERVADOS_WIN.has(stem.toUpperCase())) return "reservado_win";
  }
  return null;
}

// Nombre de equipo: 1-40 chars tras trim, sin HTML/control/invisibles.
// Espacios internos colapsados. Acepta acentos, puntuación normal.
const TEAM_MAX = 40;
const TEAM_PROHIBIDOS = /[<>]/;

export type TeamNameError = "vacio" | "muy_largo" | "control" | "invisible" | "prohibido";

export function validarNombreEquipo(nombre: string): TeamNameError | null {
  if (typeof nombre !== "string") return "vacio";
  let n = nombre.trim();
  if (!n) return "vacio";
  // Colapsa runs internas (mismo criterio backend).
  if (n.includes("  ")) n = n.split(/\s+/).join(" ");
  if (n.length > TEAM_MAX) return "muy_largo";
  for (const c of n) {
    const co = c.charCodeAt(0);
    if (co < 0x20 || co === 0x7f) return "control";
    if (INVISIBLES.test(c)) return "invisible";
    if (TEAM_PROHIBIDOS.test(c)) return "prohibido";
  }
  return null;
}

/** Forma canónica que se enviará al server. Aplica trim+colapso. */
export function normalizarNombreEquipo(nombre: string): string {
  return nombre.trim().replace(/\s+/g, " ");
}

// Usuario nuevo: charset estricto al REGISTRAR. Para login se acepta
// cualquier string (cuentas viejas pudieron registrarse con reglas viejas).
const USER_MIN = 2;
const USER_MAX = 32;
// Permite letras, dígitos, ., _, -, @, + (mismo charset que backend).
const USER_RE = /^[a-z0-9._+\-@]+$/;

export type UserError =
  | "vacio" | "muy_corto" | "muy_largo"
  | "empieza_mal" | "charset" | "reservado";

export function validarUsuarioNuevo(usuario: string): UserError | null {
  if (typeof usuario !== "string") return "vacio";
  const u = usuario.trim().toLowerCase();
  if (!u) return "vacio";
  if (u.length < USER_MIN) return "muy_corto";
  if (u.length > USER_MAX) return "muy_largo";
  if (".-_".includes(u[0])) return "empieza_mal";
  if (!USER_RE.test(u)) return "charset";
  if (u.startsWith("gh:")) return "reservado";
  return null;
}

/** Copia texto al portapapeles. Devuelve un Promise<boolean>: true=éxito,
 * false=algo falló (navegador viejo, contexto inseguro, denegado). El UI
 * decide qué mensaje mostrar según el resultado. */
export async function copiarTexto(texto: string): Promise<boolean> {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(texto);
      return true;
    }
  } catch {
    /* cae al fallback */
  }
  // Fallback: textarea oculto + execCommand. Funciona en HTTP local y
  // navegadores viejos. document.execCommand está deprecated pero sigue
  // soportado en todos los navegadores modernos para este caso.
  try {
    const ta = document.createElement("textarea");
    ta.value = texto;
    ta.style.position = "fixed";
    ta.style.left = "-9999px";
    ta.setAttribute("readonly", "");
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}
