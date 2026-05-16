import { useEffect, useLayoutEffect, useRef } from "react";
import type { ChangeEvent, KeyboardEvent } from "react";
import { useStore } from "../useStore";
import { editar, presence } from "../store";
import { resaltar } from "../lang";

// Mismo mecanismo que el cliente vanilla, ahora en un componente: textarea
// REAL transparente encima, capas sincronizadas detrás/encima por scroll.
// El textarea sigue siendo el editor de verdad (no se reemplaza), así
// presencia/locks/tentativo funcionan igual. CONTRATO con el CSS: estas
// constantes DEBEN coincidir con .ed-ta/.ed-hl (line-height 22, padding
// top 20, gutter 52). Si no, las marcas de presencia se desalinean.
const LINE_H = 22;
const PAD_TOP = 20;

export function Editor() {
  const s = useStore();
  const path = s.currentPath;
  const valor = path ? (s.files[path] ?? "") : "";

  const taRef = useRef<HTMLTextAreaElement>(null);
  const codeRef = useRef<HTMLElement>(null);
  const gutRef = useRef<HTMLDivElement>(null);
  const presRef = useRef<HTMLDivElement>(null);
  const activaRef = useRef<HTMLDivElement>(null);
  const presScrollRef = useRef<HTMLDivElement>(null);
  const selRef = useRef<{ s: number; e: number } | null>(null);
  const pendingSel = useRef<number | null>(null);
  // ¿El último cambio de `valor` lo originó ESTE cliente? Si sí, React ya
  // mantiene el caret de un textarea controlado: NO hay que tocarlo (si lo
  // tocáramos, pelearíamos con React y saltaría el cursor al tipear). Solo
  // en updates REMOTOS restauramos el caret guardado.
  const fromLocal = useRef(false);

  function lineaActual(): number {
    const ta = taRef.current;
    if (!ta) return 1;
    return ta.value.slice(0, ta.selectionStart).split("\n").length;
  }

  // Pinta resaltado + gutter + línea activa. Llamar tras cada cambio.
  function pintar() {
    const ta = taRef.current;
    if (!ta || !codeRef.current || !gutRef.current) return;
    codeRef.current.innerHTML = resaltar(ta.value, path);
    const n = ta.value.split("\n").length;
    let g = "";
    for (let i = 1; i <= n; i++) g += i + "\n";
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
    if (presScrollRef.current)
      presScrollRef.current.style.transform = `translateY(${-st}px)`;
    if (activaRef.current) {
      const ln = lineaActual();
      activaRef.current.style.top =
        PAD_TOP + (ln - 1) * LINE_H - st + "px";
    }
  }

  // Marcas de presencia de los OTROS en este archivo (no yo).
  function pintarPresencia() {
    const cont = presScrollRef.current;
    if (!cont) return;
    cont.innerHTML = "";
    if (!path) return;
    for (const p of Object.values(s.peers)) {
      if (!s.yo || p.client_id === s.yo.client_id) continue;
      if (p.path !== path) continue;
      const m = document.createElement("div");
      m.className = "marca";
      m.style.top = PAD_TOP + (p.line - 1) * LINE_H + "px";
      const tinte = document.createElement("div");
      tinte.className = "tinte";
      tinte.style.background = p.color;
      const raya = document.createElement("div");
      raya.className = "raya";
      raya.style.background = p.color;
      const et = document.createElement("div");
      et.className = "etiqueta";
      et.style.background = p.color;
      et.textContent = p.name;
      m.append(tinte, raya, et);
      cont.appendChild(m);
    }
  }

  // Repinta cuando cambia el valor / archivo (incluye updates remotos:
  // el server nunca hace eco al emisor, así que no hay loop).
  useLayoutEffect(() => {
    const ta = taRef.current;
    if (ta && pendingSel.current != null) {
      // Caso teclado (par/Tab/Enter): caret calculado por nosotros.
      ta.selectionStart = ta.selectionEnd = pendingSel.current;
      pendingSel.current = null;
    } else if (fromLocal.current) {
      // Tipeo normal: React ya conservó el caret del textarea controlado.
      // No tocar nada (tocarlo haría saltar el cursor).
    } else if (ta && selRef.current && document.activeElement === ta) {
      // Update REMOTO mientras escribías: conservá el caret (clamp).
      const max = ta.value.length;
      ta.selectionStart = Math.min(selRef.current.s, max);
      ta.selectionEnd = Math.min(selRef.current.e, max);
    }
    fromLocal.current = false;
    pintar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [valor, path]);

  useEffect(() => {
    pintarPresencia();
    sincronizarScroll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [s.peers, path, valor]);

  function guardarSel() {
    const ta = taRef.current;
    if (ta) selRef.current = { s: ta.selectionStart, e: ta.selectionEnd };
  }

  function onChange(e: ChangeEvent<HTMLTextAreaElement>) {
    if (!path) return;
    fromLocal.current = true;
    editar(path, e.target.value);
    presence(path, e.target.value.slice(0, e.target.selectionStart).split("\n").length);
  }

  // Ergonomía mínima de editor (sin librerías): pares, Tab=4, Enter mantiene
  // sangría. Calcula valor+caret y lo aplica vía store (pendingSel restaura
  // el cursor tras el re-render controlado).
  const PARES: Record<string, string> = { "(": ")", "[": "]", "{": "}", '"': '"', "'": "'", "`": "`" };
  function onKeyDown(e: KeyboardEvent<HTMLTextAreaElement>) {
    const ta = taRef.current;
    if (!ta || !path) return;
    const v = ta.value, a = ta.selectionStart, b = ta.selectionEnd;
    const aplicar = (nv: string, caret: number) => {
      e.preventDefault();
      pendingSel.current = caret;
      fromLocal.current = true;
      editar(path, nv);
      presence(path, nv.slice(0, caret).split("\n").length);
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
      aplicar(v, a + 1); // saltar el cierre ya puesto
      return;
    }
    if (e.key === "Backspace" && a === b && a > 0 && PARES[v[a - 1]] === v[a]) {
      aplicar(v.slice(0, a - 1) + v.slice(a + 1), a - 1);
      return;
    }
  }

  return (
    <div className={"editorwrap" + (path ? "" : " off")}>
      <div className="ed-active" ref={activaRef} style={{ display: path ? "block" : "none" }} />
      <pre className="ed-hl" aria-hidden="true"><code ref={codeRef} /></pre>
      <div className="ed-pres"><div className="ed-pres-scroll" ref={presScrollRef} /></div>
      <textarea
        className="ed-ta"
        ref={taRef}
        spellCheck={false}
        disabled={!path}
        placeholder="seleccioná un archivo o creá uno nuevo"
        value={valor}
        onChange={onChange}
        onKeyDown={onKeyDown}
        onScroll={sincronizarScroll}
        onKeyUp={() => { guardarSel(); sincronizarScroll(); if (path) presence(path, lineaActual()); }}
        onClick={() => { guardarSel(); sincronizarScroll(); if (path) presence(path, lineaActual()); }}
        onSelect={guardarSel}
      />
      <div className="ed-gutter"><div className="ed-gutter-scroll" ref={gutRef} /></div>
    </div>
  );
}
