import { useStore } from "../useStore";
import { salir } from "../store";

const ETIQUETA = {
  conectando: "conectando…", conectado: "conectado",
  desconectado: "desconectado", error: "error de conexión",
} as const;

export function TopBar() {
  const s = useStore();
  const clase =
    s.conn === "conectado" ? "status ok"
    : s.conn === "conectando" ? "status" : "status bad";
  return (
    <header className="topbar isla">
      <div className="mark">▣</div>
      <span className="brand">la<b>idea</b></span>
      <span className="chev">›</span>
      <span className="proy">{s.proyecto}</span>
      <span className="spacer" />
      <span className={clase}>{ETIQUETA[s.conn]}</span>
      {s.yo && (
        <span className="yo">
          <span className="dot" style={{ background: s.yo.color }} />
          {s.yo.name}
        </span>
      )}
      {s.authed && <button className="salir" onClick={salir}>salir</button>}
    </header>
  );
}
