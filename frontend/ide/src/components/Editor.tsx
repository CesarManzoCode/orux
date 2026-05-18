import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import type { ChangeEvent, KeyboardEvent } from "react";
import { useStore } from "../useStore";
import { editar, guardar, presence, setCaret } from "../store";
import { resaltar, guiasIndent } from "../lang";
import { proyectar, vistaAFull, fullAVista, cabeceras } from "../plegado";

// Mismo mecanismo que el cliente vanilla: textarea REAL transparente
// encima, capas sincronizadas detrás/encima por scroll. El textarea
// sigue siendo el editor de verdad. CONTRATO con el CSS: estas
// constantes DEBEN coincidir con .ed-ta/.ed-hl (line-height 22, padding
// top 20, gutter 52). Si no, las marcas de presencia se desalinean.
//
// PLEGADO (solo cliente, efímero): el textarea muestra la PROYECCIÓN
// (proj.vista), pero todo lo que viaja por WS es el texto COMPLETO
// (`valor`). `aplicarVista` reconstruye SIEMPRE el completo antes de
// `editar`: plegar nunca corrompe el doc compartido ni se sincroniza.
const LINE_H = 22;
const PAD_TOP = 20;

export function Editor() {
  const s = useStore();
  const path = s.currentPath;
  const valor = path ? (s.files[path] ?? "") : ""; // texto COMPLETO (verdad)

  const taRef = useRef<HTMLTextAreaElement>(null);
  const codeRef = useRef<HTMLElement>(null);
  const gutRef = useRef<HTMLDivElement>(null);
  const activaRef = useRef<HTMLDivElement>(null);
  const gutActRef = useRef<HTMLDivElement>(null);
  const presScrollRef = useRef<HTMLDivElement>(null);
  const gutMarksRef = useRef<HTMLDivElement>(null);
  const guiasRef = useRef<HTMLDivElement>(null);
  const foldsRef = useRef<HTMLDivElement>(null);
  const gutFoldRef = useRef<HTMLDivElement>(null);
  const selRef = useRef<{ s: number; e: number } | null>(null);
  // Caret pendiente, en offset del texto COMPLETO. Tras cada cambio el
  // efecto lo re-mapea a la vista actual (que pudo plegarse/cambiar).
  const pendingFullCaret = useRef<number | null>(null);
  const lastFullCaret = useRef(0);
  const fromLocal = useRef(false);

  // Pliegues: cabeceras (línea 1-based del texto completo) plegadas.
  // Estado local, efímero, jamás se envía. Se vacía al cambiar de
  // archivo (no se persiste entre sesiones, decisión del usuario).
  const [folds, setFolds] = useState<Set<number>>(new Set());
  useEffect(() => { setFolds(new Set()); }, [path]);

  // Proyección: única fuente de geometría. La recalculan `valor`
  // (cambios locales/remotos) y `folds` (clicks en las flechas).
  const proj = useMemo(() => proyectar(valor, folds), [valor, folds]);
  // Línea de vista donde está el cursor (geometría: banda/guía activa).
  const [caretVis, setCaretVis] = useState(1);

  // Flechas de plegado: una por cabecera VISIBLE (las de bloques
  // plegados quedan ocultas con su cuerpo → no estorban).
  const cabsVis = useMemo(() => {
    const cs = cabeceras(valor);
    const out: { ini: number; visLine: number; plegada: boolean }[] = [];
    for (const c of cs) {
      const vl = proj.fullToVis.get(c.ini);
      if (vl != null) out.push({ ini: c.ini, visLine: vl, plegada: folds.has(c.ini) });
    }
    return out;
  }, [valor, proj, folds]);

  function caretFullDe(): number {
    const ta = taRef.current;
    if (!ta) return 0;
    return vistaAFull(proj, ta.selectionStart);
  }
  function lineaColDe(off: number): { line: number; col: number } {
    const antes = valor.slice(0, off);
    const nl = antes.lastIndexOf("\n");
    return { line: antes.split("\n").length, col: off - nl };
  }

  // Línea/col REAL (texto completo) para status bar/inspector + línea de
  // vista para la geometría del scope. La presencia viaja con la línea
  // COMPLETA (el equipo no sabe nada de mis pliegues).
  function actualizarCaret() {
    const ta = taRef.current;
    if (!ta || !path) return;
    const off = caretFullDe();
    lastFullCaret.current = off;
    const { line, col } = lineaColDe(off);
    setCaret(line, col);
    setCaretVis(ta.value.slice(0, ta.selectionStart).split("\n").length);
    presence(path, line);
  }

  // Pinta resaltado (de la VISTA) + gutter con números REALES (saltan en
  // cada pliegue, como PyCharm) + sincroniza scroll.
  function pintar() {
    const ta = taRef.current;
    if (!ta || !codeRef.current || !gutRef.current) return;
    codeRef.current.innerHTML = resaltar(ta.value, path);
    let g = "";
    for (const f of proj.visToFull) g += f + "\n";
    gutRef.current.textContent = g;
    sincronizarScroll();
  }

  function sincronizarScroll() {
    const ta = taRef.current;
    if (!ta) return;
    const st = ta.scrollTop, sl = ta.scrollLeft;
    if (codeRef.current)
      codeRef.current.style.transform = `translate(${-sl}px, ${-st}px)`;
    if (gutRef.current)
      gutRef.current.style.transform = `translateY(${-st}px)`;
    if (gutFoldRef.current)
      gutFoldRef.current.style.transform = `translateY(${-st}px)`;
    if (presScrollRef.current)
      presScrollRef.current.style.transform = `translateY(${-st}px)`;
    if (gutMarksRef.current)
      gutMarksRef.current.style.transform = `translateY(${-st}px)`;
    if (guiasRef.current)
      guiasRef.current.style.transform = `translate(${-sl}px, ${-st}px)`;
    if (foldsRef.current)
      foldsRef.current.style.transform = `translate(${-sl}px, ${-st}px)`;
    if (activaRef.current || gutActRef.current) {
      const ln = ta.value.slice(0, ta.selectionStart).split("\n").length;
      const y = PAD_TOP + (ln - 1) * LINE_H - st + "px";
      if (activaRef.current) activaRef.current.style.top = y;
      if (gutActRef.current) gutActRef.current.style.top = y;
    }
  }

  // Presencia de los OTROS. Su línea es COMPLETA: la mapeo a la vista.
  // Si cae dentro de un bloque que YO plegué, no la escondo en silencio
  // (rompería la tesis "el sistema sabe"): la subo a la cabecera visible
  // y la marco como "en bloque plegado" para no perder al compañero.
  function pintarPresencia() {
    const cont = presScrollRef.current;
    const gut = gutMarksRef.current;
    if (gut) gut.innerHTML = "";
    if (!cont) return;
    cont.innerHTML = "";
    if (!path) return;
    for (const p of Object.values(s.peers)) {
      if (!s.yo || p.client_id === s.yo.client_id) continue;
      if (p.path !== path) continue;
      const visDirecto = proj.fullToVis.get(p.line);
      let vl: number;
      let oculto = false;
      if (visDirecto != null) {
        vl = visDirecto;
      } else {
        oculto = true;
        let cab = 0;
        for (let g = p.line; g >= 1; g--) {
          const v = proj.fullToVis.get(g);
          if (v != null) { cab = v; break; }
        }
        vl = cab;
      }
      const top = PAD_TOP + vl * LINE_H;
      if (gut) {
        const d = document.createElement("div");
        d.className = "gmark" + (oculto ? " oculto" : "");
        d.style.top = top + "px";
        d.style.background = p.color;
        if (oculto) d.style.color = p.color; // anillo = color del peer
        d.title = p.name + " · línea " + p.line + (oculto ? " (bloque plegado)" : "");
        gut.appendChild(d);
      }
      const m = document.createElement("div");
      m.className = "marca" + (oculto ? " oculto" : "");
      m.style.top = top + "px";
      const tinte = document.createElement("div");
      tinte.className = "tinte";
      tinte.style.background = p.color;
      const raya = document.createElement("div");
      raya.className = "raya";
      raya.style.background = p.color;
      const et = document.createElement("div");
      et.className = "etiqueta";
      et.style.background = p.color;
      et.textContent = p.name + (oculto ? " · ⋯" : "");
      m.append(tinte, raya, et);
      cont.appendChild(m);
    }
  }

  // Tras cada cambio (local o remoto) o re-plegado: restaurar caret en
  // la VISTA actual mapeando desde el offset COMPLETO guardado.
  useLayoutEffect(() => {
    const ta = taRef.current;
    if (ta) {
      const max = ta.value.length;
      if (pendingFullCaret.current != null) {
        const o = Math.min(fullAVista(proj, pendingFullCaret.current), max);
        ta.selectionStart = ta.selectionEnd = o;
        pendingFullCaret.current = null;
      } else if (!fromLocal.current && selRef.current && document.activeElement === ta) {
        // Update REMOTO mientras escribías: reanclá por el último caret
        // completo conocido (clamp), mapeado a la vista nueva.
        const o = Math.min(fullAVista(proj, lastFullCaret.current), max);
        ta.selectionStart = ta.selectionEnd = o;
      }
    }
    fromLocal.current = false;
    pintar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [proj, path]);

  useEffect(() => {
    pintarPresencia();
    sincronizarScroll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.peers, path, proj]);

  function guardarSel() {
    const ta = taRef.current;
    if (ta) selRef.current = { s: ta.selectionStart, e: ta.selectionEnd };
  }

  // El CORAZÓN del plegado: una mutación de la VISTA se reconstruye al
  // texto COMPLETO (prefijo/sufijo común + mapa de offsets) y recién eso
  // se manda. Si la edición toca un borde de pliegue, el mapa hace lo
  // correcto (PyCharm: borrar el borde borra el bloque plegado entero).
  function aplicarVista(nuevaVista: string, caretVista: number) {
    if (!path) return;
    const old = proj.vista;
    let p = 0;
    const minLen = Math.min(old.length, nuevaVista.length);
    while (p < minLen && old[p] === nuevaVista[p]) p++;
    let q = 0;
    while (
      q < minLen - p &&
      old[old.length - 1 - q] === nuevaVista[nuevaVista.length - 1 - q]
    ) q++;
    const fullStart = vistaAFull(proj, p);
    const fullEnd = vistaAFull(proj, old.length - q);
    const insertado = nuevaVista.slice(p, nuevaVista.length - q);
    const nuevoFull = valor.slice(0, fullStart) + insertado + valor.slice(fullEnd);
    let caretFull: number;
    if (caretVista <= p) caretFull = vistaAFull(proj, caretVista);
    else if (caretVista >= nuevaVista.length - q)
      caretFull = nuevoFull.length - (nuevaVista.length - caretVista);
    else caretFull = fullStart + (caretVista - p);
    fromLocal.current = true;
    pendingFullCaret.current = caretFull;
    lastFullCaret.current = caretFull;
    editar(path, nuevoFull);
    const { line } = lineaColDe(caretFull);
    presence(path, line);
  }

  function onChange(e: ChangeEvent<HTMLTextAreaElement>) {
    aplicarVista(e.target.value, e.target.selectionStart);
  }

  // Ergonomía mínima (sin librerías), ahora en espacio de VISTA: el
  // resultado pasa por aplicarVista (reconstruye el completo).
  const PARES: Record<string, string> = { "(": ")", "[": "]", "{": "}", '"': '"', "'": "'", "`": "`" };
  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    const ta = taRef.current;
    if (!ta || !path) return;
    if ((e.ctrlKey || e.metaKey) && (e.key === "s" || e.key === "S")) {
      e.preventDefault();
      guardar(path);
      return;
    }
    const v = ta.value, a = ta.selectionStart, b = ta.selectionEnd;
    const aplicar = (nv: string, caret: number) => {
      e.preventDefault();
      aplicarVista(nv, caret);
    };
    if (e.key === "Tab") {
      aplicar(v.slice(0, a) + "    " + v.slice(b), a + 4);
      return;
    }
    if (e.key === "Enter") {
      const ini = v.lastIndexOf("\n", a - 1) + 1;
      const sangria = (v.slice(ini, a).match(/^[ \t]*/) || [""])[0];
      aplicar(v.slice(0, a) + "\n" + sangria + v.slice(b), a + 1 + sangria.length);
      return;
    }
    if (PARES[e.key] && a === b) {
      const cierre = PARES[e.key];
      aplicar(v.slice(0, a) + e.key + cierre + v.slice(b), a + 1);
      return;
    }
    if ((e.key === ")" || e.key === "]" || e.key === "}") && v[a] === e.key && a === b) {
      aplicar(v, a + 1);
      return;
    }
    if (e.key === "Backspace" && a === b && a > 0 && PARES[v[a - 1]] === v[a]) {
      aplicar(v.slice(0, a - 1) + v.slice(a + 1), a - 1);
      return;
    }
  }

  // Click en la flecha: alterna el pliegue. Preservo el caret por su
  // offset COMPLETO; el efecto lo re-mapea a la vista nueva (si quedó
  // dentro del bloque plegado, fullAVista lo sube a la cabecera).
  function toggleFold(ini: number) {
    pendingFullCaret.current = lastFullCaret.current;
    setFolds((prev) => {
      const n = new Set(prev);
      if (n.has(ini)) n.delete(ini); else n.add(ini);
      return n;
    });
  }

  const totalLineas = Math.max(1, valor.split("\n").length);
  const overview = path
    ? Object.values(s.peers)
        .filter((p) => p.path === path && (!s.yo || p.client_id !== s.yo.client_id))
        .map((p) => ({
          id: p.client_id, color: p.color, name: p.name,
          top: Math.min(99, ((p.line - 1) / totalLineas) * 100),
        }))
    : [];

  // Guías de indentación reales: una por nivel, SÓLO dentro de bloques
  // (reemplazan la rejilla CSS full-screen que se veía de juguete). Se
  // calculan sobre la VISTA (geometría = vista) y la del scope del
  // cursor se enciende, como en PyCharm.
  const guias = useMemo(() => guiasIndent(proj.vista), [proj.vista]);
  const scopeCol = useMemo(() => {
    let max = -1;
    for (const g of guias)
      if (caretVis >= g.linea && caretVis < g.linea + g.alto && g.col > max)
        max = g.col;
    return max;
  }, [guias, caretVis]);

  return (
    <div className={"editorwrap" + (path ? "" : " off")}>
      <div className="ed-active" ref={activaRef} style={{ display: path ? "block" : "none" }} />
      <pre className="ed-hl" aria-hidden="true"><code ref={codeRef} /></pre>
      {path && (
        <div className="ed-guides" aria-hidden="true">
          <div className="ed-guides-scroll" ref={guiasRef}>
            {guias.map((g, i) => {
              const activa =
                scopeCol === g.col &&
                caretVis >= g.linea &&
                caretVis < g.linea + g.alto;
              return (
                <div
                  key={i}
                  className={"ed-guide-line" + (activa ? " activa" : "")}
                  style={{
                    left: `calc(64px + ${g.col}ch)`,
                    top: PAD_TOP + (g.linea - 1) * LINE_H + "px",
                    height: g.alto * LINE_H + "px",
                  }}
                />
              );
            })}
          </div>
        </div>
      )}
      {path && proj.plegadasVisibles.length > 0 && (
        <div className="ed-folds" aria-hidden="true">
          <div className="ed-folds-scroll" ref={foldsRef}>
            {proj.plegadasVisibles.map(({ cab, visLine }) => {
              const txt = valor.split("\n")[cab.ini - 1] ?? "";
              return (
                <span
                  key={cab.ini}
                  className="ed-foldmark"
                  style={{
                    left: `calc(64px + ${txt.length + 1}ch)`,
                    top: PAD_TOP + visLine * LINE_H + "px",
                  }}
                >
                  ⋯
                </span>
              );
            })}
          </div>
        </div>
      )}
      <div className="ed-pres"><div className="ed-pres-scroll" ref={presScrollRef} /></div>
      <textarea
        className="ed-ta"
        ref={taRef}
        spellCheck={false}
        disabled={!path}
        placeholder="seleccioná un archivo o creá uno nuevo"
        value={proj.vista}
        onChange={onChange}
        onKeyDown={onKeyDown}
        onScroll={sincronizarScroll}
        onKeyUp={() => { guardarSel(); sincronizarScroll(); actualizarCaret(); }}
        onClick={() => { guardarSel(); sincronizarScroll(); actualizarCaret(); }}
        onSelect={guardarSel}
      />
      <div className="ed-gutter">
        <div
          className="ed-gutter-active"
          ref={gutActRef}
          style={{ display: path ? "block" : "none" }}
        />
        <div className="ed-gutter-scroll" ref={gutRef} />
        {path && cabsVis.length > 0 && (
          <div className="ed-gutter-fold" ref={gutFoldRef}>
            {cabsVis.map((c) => (
              <button
                key={c.ini}
                type="button"
                className={"ed-chevron" + (c.plegada ? " plegada" : "")}
                style={{ top: PAD_TOP + c.visLine * LINE_H + "px" }}
                title={c.plegada ? "Expandir bloque" : "Contraer bloque"}
                onMouseDown={(ev) => ev.preventDefault()}
                onClick={() => toggleFold(c.ini)}
              >
                <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">
                  <path d="M3 4.5 L6 7.5 L9 4.5" fill="none"
                    stroke="currentColor" strokeWidth="1.6"
                    strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </button>
            ))}
          </div>
        )}
        <div className="ed-gutter-marks" ref={gutMarksRef} />
      </div>
      {path && overview.length > 0 && (
        <div className="ed-overview" aria-hidden="true">
          {overview.map((o) => (
            <span
              key={o.id}
              className="ovmark"
              style={{ top: o.top + "%", background: o.color }}
              title={o.name}
            />
          ))}
        </div>
      )}
    </div>
  );
}
