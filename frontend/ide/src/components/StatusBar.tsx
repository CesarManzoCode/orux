import { useStore } from "../useStore";
import { chipDe } from "../lang";

const CONN = {
  conectando: "conectando…", conectado: "en línea",
  desconectado: "sin conexión", error: "error",
} as const;

// Capa 26 — Status bar de instrumento: dos alas con segmentos separados
// por hairlines. Izquierda = repo/sync (estado del mundo). Derecha =
// archivo/posición/identidad (dónde estás). Sólo lee estado que ya
// existe + el caret local. Densa, tabular, sin gritar.
export function StatusBar() {
  const s = useStore();
  const g = s.git;
  const enLinea = Object.keys(s.peers).length + (s.yo ? 1 : 0);
  const propsParaMi = Object.values(s.proposals).filter(
    (p) => s.yo && s.owners[p.path] === s.yo.client_id,
  ).length;
  const lang = s.currentPath ? chipDe(s.currentPath).nom : "—";
  const connClase =
    s.conn === "conectado" ? "ok" : s.conn === "conectando" ? "" : "bad";

  return (
    <footer className="statusbar isla">
      <span className={"sb conn " + connClase}>
        <span className="sb-led" />
        {CONN[s.conn]}
      </span>
      <span className="sb-div" />
      <span className="sb">
        ⎇ <b>{g && g.available ? (g.branch || "—") : "sin git"}</b>
      </span>
      {g && g.available && (
        <>
          <span className="sb-div" />
          <span className={"sb" + (g.changes ? " acc-warn" : "")}>
            {g.changes === 0
              ? "limpio"
              : g.changes + (g.changes === 1 ? " cambio" : " cambios")}
          </span>
        </>
      )}
      {propsParaMi > 0 && (
        <>
          <span className="sb-div" />
          <span className="sb acc-info" title="propuestas que esperan tu revisión">
            {propsParaMi} para revisar
          </span>
        </>
      )}

      <span className="spacer" />

      <span className="sb">
        <span className="sb-live" /> {enLinea} en línea
      </span>
      <span className="sb-div" />
      <span className="sb">{lang}</span>
      {s.currentPath && (
        <>
          <span className="sb-div" />
          <span className="sb tabnum">
            Ln {s.caret.line}, Col {s.caret.col}
          </span>
          <span className="sb-div" />
          <span className="sb">4 esp · UTF-8</span>
        </>
      )}
      <span className="sb-div" />
      <span className="sb">
        {s.yo && <span className="sb-pt" style={{ background: s.yo.color }} />}
        {s.yo ? s.yo.name : "—"}
      </span>
    </footer>
  );
}
