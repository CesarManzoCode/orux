import { useStore } from "../useStore";
import { chipDe } from "../lang";

// Barra de estado inferior: rama · cambios · lenguaje · identidad. Sólo
// lee estado que ya existe. Señal fuerte de "herramienta real".
export function StatusBar() {
  const s = useStore();
  const g = s.git;
  return (
    <footer className="statusbar isla">
      <span className="sb">
        {g && g.available ? (
          <>
            ⎇ <b>{g.branch || "—"}</b>
            <span className="sep">·</span>
            {g.changes === 0 ? "limpio" : g.changes + (g.changes === 1 ? " cambio" : " cambios")}
          </>
        ) : "sin git"}
      </span>
      <span className="spacer" />
      {(() => {
        const n = Object.keys(s.peers).length + (s.yo ? 1 : 0);
        return (
          <>
            <span className="sb">
              <span className="vivo" /> {n} en línea
            </span>
            <span className="sep">·</span>
          </>
        );
      })()}
      <span className="sb">{s.currentPath ? chipDe(s.currentPath).nom : "—"}</span>
      <span className="sep">·</span>
      <span className="sb">
        {s.yo && <span className="pt" style={{ background: s.yo.color }} />}
        {s.yo ? s.yo.name : "—"}
      </span>
    </footer>
  );
}
