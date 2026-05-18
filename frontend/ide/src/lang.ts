// Helpers puros portados del cliente vanilla (capa de pulido + 11 + chrome):
// lenguaje por extensión, chip de tipo, resaltado Prism con degradación,
// árbol de carpetas y diff por líneas. Sin estado, sin React: lógica que
// ya estaba probada en producción, sólo movida a TS.

import Prism from "prismjs";
import "prismjs/components/prism-markup";
import "prismjs/components/prism-css";
import "prismjs/components/prism-clike";
import "prismjs/components/prism-javascript";
import "prismjs/components/prism-python";
import "prismjs/components/prism-json";
import "prismjs/components/prism-bash";
import "prismjs/components/prism-yaml";
import "prismjs/components/prism-sql";
import "prismjs/components/prism-java";
import "prismjs/components/prism-go";
import "prismjs/components/prism-rust";
import "prismjs/components/prism-c";
import "prismjs/components/prism-cpp";
import "prismjs/components/prism-kotlin";
import "prismjs/components/prism-typescript";
import "prismjs/components/prism-jsx";
import "prismjs/components/prism-tsx";
import "prismjs/components/prism-markdown";
import "prismjs/components/prism-docker";
import "prismjs/components/prism-makefile";

const LANG: Record<string, string> = {
  ts: "typescript", tsx: "tsx", js: "javascript", jsx: "jsx",
  mjs: "javascript", cjs: "javascript", py: "python", json: "json",
  css: "css", scss: "css", html: "markup", htm: "markup", xml: "markup",
  svg: "markup", vue: "markup", md: "markdown", markdown: "markdown",
  sh: "bash", bash: "bash", yml: "yaml", yaml: "yaml", toml: "yaml",
  sql: "sql", java: "java", go: "go", rs: "rust",
  c: "c", h: "c", cpp: "cpp", cc: "cpp", cxx: "cpp", hpp: "cpp",
  hxx: "cpp", kt: "kotlin", kts: "kotlin", dockerfile: "docker",
};
// Archivos sin extensión que igual son código.
const NOMBRE: Record<string, string> = { dockerfile: "docker", makefile: "makefile" };

export function langDe(path: string | null): string | null {
  if (!path) return null;
  const base = path.split("/").pop()!.toLowerCase();
  for (const k in NOMBRE) {
    if (base === k || base.startsWith(k + ".") || base.endsWith("." + k)) {
      return NOMBRE[k];
    }
  }
  const i = base.lastIndexOf(".");
  if (i < 0) return null;
  return LANG[base.slice(i + 1)] || null;
}

// Lenguaje -> [texto del chip, clase de color, nombre legible].
const CHIP: Record<string, [string, string, string]> = {
  python: ["py", "t-py", "Python"],
  typescript: ["ts", "t-ts", "TypeScript"], tsx: ["tsx", "t-ts", "TSX"],
  javascript: ["js", "t-js", "JavaScript"], jsx: ["jsx", "t-js", "JSX"],
  go: ["go", "t-go", "Go"], rust: ["rs", "t-rs", "Rust"],
  java: ["java", "t-java", "Java"], kotlin: ["kt", "t-java", "Kotlin"],
  cpp: ["cpp", "t-cpp", "C++"], c: ["c", "t-cpp", "C"],
  markdown: ["md", "t-md", "Markdown"],
  json: ["json", "t-cfg", "JSON"], yaml: ["yml", "t-cfg", "YAML"],
  docker: ["dok", "t-cfg", "Dockerfile"], makefile: ["mk", "t-cfg", "Makefile"],
  bash: ["sh", "t-cfg", "Shell"], sql: ["sql", "t-cfg", "SQL"],
  markup: ["<>", "t-cfg", "Markup"], css: ["css", "t-cfg", "CSS"],
};

export function chipDe(path: string | null): { txt: string; cls: string; nom: string } {
  const lang = langDe(path);
  if (lang && CHIP[lang]) {
    const [txt, cls, nom] = CHIP[lang];
    return { txt, cls, nom };
  }
  const base = (path || "").split("/").pop() || "";
  const ext = base.includes(".") ? base.split(".").pop()!.toLowerCase() : "";
  return { txt: (ext || "·").slice(0, 4), cls: "", nom: ext || "texto" };
}

// Resaltado: Prism si hay gramática; si algo falla, texto plano escapado.
// NUNCA lanza (un resaltador roto jamás debe tumbar el editor — lección
// dura ya vivida con el bundle de Prism).
export function escHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
export function resaltar(texto: string, path: string | null): string {
  const lang = langDe(path);
  try {
    if (lang && Prism.languages[lang]) {
      return Prism.highlight(texto, Prism.languages[lang], lang);
    }
  } catch {
    /* degradación: texto plano */
  }
  return escHtml(texto);
}

// Árbol de carpetas a partir de los paths.
export interface Nodo {
  dirs: Record<string, Nodo>;
  files: { nombre: string; path: string }[];
}
export function arbol(paths: string[]): Nodo {
  const raiz: Nodo = { dirs: {}, files: [] };
  for (const p of paths) {
    const partes = p.split("/");
    let nodo = raiz;
    for (let i = 0; i < partes.length - 1; i++) {
      nodo.dirs[partes[i]] = nodo.dirs[partes[i]] || { dirs: {}, files: [] };
      nodo = nodo.dirs[partes[i]];
    }
    nodo.files.push({ nombre: partes[partes.length - 1], path: p });
  }
  return raiz;
}
export function archivosDe(nodo: Nodo): string[] {
  let out = nodo.files.map((f) => f.path);
  for (const d of Object.keys(nodo.dirs)) out = out.concat(archivosDe(nodo.dirs[d]));
  return out;
}

// Diff por líneas (LCS) — mismo algoritmo que la bandeja de propuestas.
export type Fila = { t: "eq" | "add" | "del"; x: string };
export function diffLineas(viejo: string, nuevo: string): Fila[] {
  const a = viejo.split("\n"), b = nuevo.split("\n");
  const n = a.length, m = b.length;
  const lcs = Array.from({ length: n + 1 }, () => new Array(m + 1).fill(0));
  for (let i = n - 1; i >= 0; i--)
    for (let j = m - 1; j >= 0; j--)
      lcs[i][j] = a[i] === b[j]
        ? lcs[i + 1][j + 1] + 1
        : Math.max(lcs[i + 1][j], lcs[i][j + 1]);
  const filas: Fila[] = [];
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) { filas.push({ t: "eq", x: a[i] }); i++; j++; }
    else if (lcs[i + 1][j] >= lcs[i][j + 1]) { filas.push({ t: "del", x: a[i] }); i++; }
    else { filas.push({ t: "add", x: b[j] }); j++; }
  }
  while (i < n) filas.push({ t: "del", x: a[i++] });
  while (j < m) filas.push({ t: "add", x: b[j++] });
  return filas;
}

// Guías de indentación estilo IDE pro (PyCharm/VSCode): UNA línea vertical
// por nivel de bloque, dibujada SÓLO donde hay bloque — no una rejilla
// full-screen como el hack CSS anterior (eso era lo que se veía "toy").
// Las líneas en blanco heredan el nivel MÍNIMO de sus vecinas no vacías:
// así la guía cruza los huecos internos de un bloque pero NO se extiende
// más allá de su fin. Pura, sin estado: la geometría la pone el Editor.
const INDENT = 4;
export interface Guia { col: number; linea: number; alto: number }
export function guiasIndent(texto: string): Guia[] {
  const lineas = texto.split("\n");
  const n = lineas.length;
  // nivel por línea; null = en blanco (se resuelve por vecindad después)
  const nivel: (number | null)[] = lineas.map((l) => {
    if (l.trim() === "") return null;
    let sp = 0;
    for (const c of l) {
      if (c === " ") sp++;
      else if (c === "\t") sp += INDENT;
      else break;
    }
    return Math.floor(sp / INDENT);
  });
  const res: number[] = new Array(n).fill(0);
  for (let i = 0; i < n; i++) {
    if (nivel[i] != null) { res[i] = nivel[i]!; continue; }
    let p = i - 1; while (p >= 0 && nivel[p] == null) p--;
    let q = i + 1; while (q < n && nivel[q] == null) q++;
    const a = p >= 0 ? nivel[p]! : 0;
    const b = q < n ? nivel[q]! : 0;
    res[i] = Math.min(a, b);
  }
  // Por cada columna de indentación k, agrupar las corridas verticales
  // de líneas cuyo nivel la supera = un segmento de guía contiguo.
  let maxLv = 0;
  for (const v of res) if (v > maxLv) maxLv = v;
  const guias: Guia[] = [];
  for (let k = 0; k < maxLv; k++) {
    let i = 0;
    while (i < n) {
      if (res[i] > k) {
        let j = i;
        while (j < n && res[j] > k) j++;
        guias.push({ col: k * INDENT, linea: i + 1, alto: j - i });
        i = j;
      } else i++;
    }
  }
  return guias;
}

// Nivel de indentación resuelto de UNA línea (1-based) — para saber qué
// guía es la del bloque que contiene al cursor (se resalta como en
// PyCharm: la del scope activo brilla, el resto recede).
export function nivelLinea(texto: string, linea1: number): number {
  const g = guiasIndent(texto);
  let max = -1;
  for (const x of g) {
    if (linea1 >= x.linea && linea1 < x.linea + x.alto && x.col > max) max = x.col;
  }
  return max; // columna de la guía más interna que lo envuelve, -1 si ninguna
}

// Inicial para los puntos de presencia.
export function inicial(name: string): string {
  const m = name.match(/(\d+)$/);
  return m ? m[1] : name.slice(0, 2);
}
