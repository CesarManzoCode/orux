import { useStore } from "../useStore";
import { salir, crearInvite } from "../store";

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
      {/* Capa 15: el breadcrumb muestra el EQUIPO actual (no el host). */}
      <span className="proy">{s.equipo ? s.equipo.nombre : s.proyecto}</span>
      <span className="spacer" />
      {/* Sólo el admin del equipo puede invitar; el código aparece inline
          para copiarlo y pasarlo (un solo uso). */}
      {s.equipo?.rol === "admin" && (
        s.inviteCode ? (
          <span className="yo" title="código de un solo uso — compartilo">
            invitar: <code style={{ color: "var(--accent)" }}>{s.inviteCode}</code>
          </span>
        ) : (
          <button className="salir" onClick={crearInvite}>invitar</button>
        )
      )}
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
