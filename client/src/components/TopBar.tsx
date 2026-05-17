import { useStore } from "../useStore";
import { salir, crearInvite } from "../store";

const ETIQUETA = {
  conectando: "conectando…", conectado: "conectado",
  desconectado: "desconectado", error: "error de conexión",
} as const;

function iniciales(n: string): string {
  const p = n.replace(/@.*/, "").split(/[.\s_-]+/).filter(Boolean);
  return ((p[0]?.[0] ?? "?") + (p[1]?.[0] ?? "")).toUpperCase();
}

export function TopBar() {
  const s = useStore();
  const clase =
    s.conn === "conectado" ? "status ok"
    : s.conn === "conectando" ? "status" : "status bad";
  // Presencia del equipo: TODOS menos yo. Es la señal de "multiplayer".
  const otros = Object.values(s.peers).filter(
    (p) => !s.yo || p.client_id !== s.yo.client_id,
  );
  const visibles = otros.slice(0, 4);
  const extra = otros.length - visibles.length;
  return (
    <header className="topbar isla">
      <div className="mark">▣</div>
      <span className="brand">la<b>idea</b></span>
      <span className="chev">›</span>
      {/* Capa 15: el breadcrumb muestra el EQUIPO actual (no el host). */}
      <span className="proy">{s.equipo ? s.equipo.nombre : s.proyecto}</span>
      {visibles.length > 0 && (
        <span
          className="peers"
          title={otros.map((p) => p.name).join(", ")}
        >
          {visibles.map((p) => (
            <span
              key={p.client_id}
              className="av"
              style={{ background: p.color }}
              title={p.name}
            >
              {iniciales(p.name)}
            </span>
          ))}
          {extra > 0 && <span className="av mas">+{extra}</span>}
        </span>
      )}
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
