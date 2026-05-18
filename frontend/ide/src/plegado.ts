// ── Plegado de bloques: capa de PROYECCIÓN, pura y solo-cliente ───────
//
// Por qué existe este módulo: el editor es colaborativo. El textarea es
// la FUENTE DE VERDAD que se sincroniza por WS (texto completo, 1 línea
// = 1 línea). El plegado NO puede tocar eso. La solución es una sola
// proyección: dado el texto completo + qué cabeceras están plegadas,
// produce la "vista" (lo que el textarea muestra) y los mapas de offset
// vista↔completo. TODOS los overlays (gutter, guías, presencia, banda
// activa) consumen ESTE mapa y nada más — así la geometría sagrada
// (LINE_H/PAD_TOP) no se toca: solo cambia QUÉ número de línea recibe.
//
// El plegado es estado local efímero: no se persiste, no viaja, el
// equipo ni se entera. Lo único innegociable: editar reconstruye SIEMPRE
// el texto completo (ver Editor.aplicarVista), nunca se manda la vista.

const INDENT = 4;

// Nivel de indentación resuelto por línea: las líneas en blanco heredan
// el MÍNIMO de sus vecinas no vacías. Así un bloque "contiene" sus
// líneas en blanco internas, pero la blanca que separa dos bloques al
// nivel de afuera NO se traga (resuelve al nivel bajo). Mismo criterio
// que las guías de indentación → cabeceras y guías siempre coinciden.
function nivelesResueltos(lineas: string[]): number[] {
  const n = lineas.length;
  const crudo: (number | null)[] = lineas.map((l) => {
    if (l.trim() === "") return null;
    let sp = 0;
    for (const c of l) {
      if (c === " ") sp++;
      else if (c === "\t") sp += INDENT;
      else break;
    }
    return Math.floor(sp / INDENT);
  });
  const res = new Array(n).fill(0);
  for (let i = 0; i < n; i++) {
    if (crudo[i] != null) { res[i] = crudo[i]!; continue; }
    let p = i - 1; while (p >= 0 && crudo[p] == null) p--;
    let q = i + 1; while (q < n && crudo[q] == null) q++;
    res[i] = Math.min(p >= 0 ? crudo[p]! : 0, q < n ? crudo[q]! : 0);
  }
  return res;
}

// Una cabecera plegable = una línea cuyo bloque (las líneas siguientes
// MÁS indentadas) tiene al menos un renglón. ini/fin son 1-based; el
// cuerpo oculto al plegar es ini+1 .. fin. Heurístico por indentación,
// sin compilador — igual que el resto del editor (vale para todo
// lenguaje con sangría: py, js, ts, json…).
export interface Cabecera { ini: number; fin: number }
export function cabeceras(texto: string): Cabecera[] {
  const lineas = texto.split("\n");
  const res = nivelesResueltos(lineas);
  const n = lineas.length;
  const out: Cabecera[] = [];
  for (let i = 0; i < n; i++) {
    if (lineas[i].trim() === "") continue;
    const li = res[i];
    let j = i + 1;
    while (j < n && res[j] > li) j++;
    if (j > i + 1) out.push({ ini: i + 1, fin: j }); // fin = última (1-based)
  }
  return out;
}

export interface Proyeccion {
  vista: string;
  // línea de vista (0-based) -> línea completa (1-based)
  visToFull: number[];
  // línea completa (1-based) -> línea de vista (0-based) si es visible
  fullToVis: Map<number, number>;
  // cabecera plegada y aún visible -> su línea de vista (para la flecha
  // y el indicador "{…}")
  plegadasVisibles: { cab: Cabecera; visLine: number }[];
  totalFull: number;
  // offsets de inicio de cada línea (1-based) en el texto completo y en
  // la vista (0-based) — base de los mapas de caret.
  fullLineStart: number[]; // idx 1..totalFull
  visLineStart: number[];  // idx 0..visToFull.length-1
}

export function proyectar(texto: string, foldStarts: Set<number>): Proyeccion {
  const lineasFull = texto.split("\n");
  const N = lineasFull.length;
  const cabs = cabeceras(texto);
  const porIni = new Map<number, Cabecera>();
  for (const c of cabs) porIni.set(c.ini, c);

  // Líneas ocultas = unión de cuerpos de cabeceras plegadas que SIGAN
  // siendo cabeceras (si una edición/cambio remoto la deshizo, el
  // pliegue se cae solo — sin persistencia ni anclaje frágil).
  const oculta = new Array(N + 1).fill(false);
  for (const ini of foldStarts) {
    const c = porIni.get(ini);
    if (!c) continue;
    for (let l = c.ini + 1; l <= c.fin; l++) oculta[l] = true;
  }

  const visToFull: number[] = [];
  const fullToVis = new Map<number, number>();
  const visLineasTxt: string[] = [];
  for (let f = 1; f <= N; f++) {
    if (oculta[f]) continue;
    fullToVis.set(f, visToFull.length);
    visToFull.push(f);
    visLineasTxt.push(lineasFull[f - 1]);
  }
  const vista = visLineasTxt.join("\n");

  // Offsets de inicio de línea, AMBOS 0-based (idx k = línea k+1):
  // longitud + 1 por el "\n". La simetría evita off-by-one en los mapas.
  const fullLineStart = new Array(N + 1).fill(0);
  for (let f = 0; f < N; f++)
    fullLineStart[f + 1] = fullLineStart[f] + lineasFull[f].length + 1;
  const visLineStart = new Array(visLineasTxt.length + 1).fill(0);
  for (let j = 0; j < visLineasTxt.length; j++)
    visLineStart[j + 1] = visLineStart[j] + visLineasTxt[j].length + 1;

  const plegadasVisibles: { cab: Cabecera; visLine: number }[] = [];
  for (const ini of foldStarts) {
    const c = porIni.get(ini);
    if (!c) continue;
    const vl = fullToVis.get(c.ini);
    if (vl != null) plegadasVisibles.push({ cab: c, visLine: vl });
  }

  return {
    vista, visToFull, fullToVis, plegadasVisibles,
    totalFull: N, fullLineStart, visLineStart,
  };
}

// ── Mapas de caret/offset ────────────────────────────────────────────
// Una columna dentro de una línea visible es COPIA VERBATIM de la línea
// completa, así que la columna se mapea 1:1; solo cambia la línea.

function lineaDeOffset(starts: number[], hasta: number, off: number): number {
  // mayor índice cuyo start <= off (búsqueda lineal acotada; los
  // archivos del editor no son enormes y esto corre por pulsación).
  let i = 0;
  while (i + 1 < hasta && starts[i + 1] <= off) i++;
  return i;
}

// offset en la VISTA -> offset en el texto COMPLETO.
export function vistaAFull(p: Proyeccion, off: number): number {
  if (p.visToFull.length === 0) return 0;
  const j = lineaDeOffset(p.visLineStart, p.visToFull.length, off);
  const col = off - p.visLineStart[j];
  const f = p.visToFull[j]; // 1-based
  return p.fullLineStart[f - 1] + col;
}

// offset en el texto COMPLETO -> offset en la VISTA. Si cae en una línea
// oculta devuelve el offset del inicio de su cabecera visible (snap):
// el caret nunca queda "dentro" de algo plegado.
export function fullAVista(p: Proyeccion, off: number): number {
  const k = lineaDeOffset(p.fullLineStart, p.totalFull, off); // 0-based
  const f = k + 1; // línea completa 1-based
  const vis = p.fullToVis.get(f);
  if (vis == null) {
    // línea oculta: snap al inicio de la cabecera visible que la contiene.
    for (let g = f; g >= 1; g--) {
      const v = p.fullToVis.get(g);
      if (v != null) return p.visLineStart[v];
    }
    return 0;
  }
  const col = off - p.fullLineStart[k];
  return p.visLineStart[vis] + col;
}
