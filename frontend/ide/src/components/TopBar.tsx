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

// Logomark propio (no un ícono de librería: eso se ve genérico). Dos
// cuadros redondeados que se solapan = "varias manos, un workspace", la
// tesis multiplayer en una forma sobria y escalable. El gradiente de
// marca vive SOLO acá y en el CTA primario.
function Logomark() {
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <defs>
        <linearGradient id="lm-grad" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
          <stop stopColor="#4cc38a" />
          <stop offset="1" stopColor="#34d9bf" />
        </linearGradient>
      </defs>
      <rect x="3.6" y="3.6" width="11.6" height="11.6" rx="3.2"
        stroke="#5b606e" strokeWidth="1.7" />
      <rect x="8.8" y="8.8" width="11.6" height="11.6" rx="3.2"
        fill="url(#lm-grad)" />
    </svg>
  );
}

// La topbar como cabina: tres grupos separados por divisores hairline en
// vez de un río de elementos sueltos. Izquierda = identidad/contexto
// (marca · equipo). Centro = presencia del equipo (el diferenciador,
// first-class). Derecha = estado de sesión + acciones, de menor peso.
export function TopBar() {
  const s = useStore();
  const clase =
    s.conn === "conectado" ? "status ok"
    : s.conn === "conectando" ? "status" : "status bad";
  // Presencia del equipo: TODOS menos yo. La señal de "multiplayer".
  const otros = Object.values(s.peers).filter(
    (p) => !s.yo || p.client_id !== s.yo.client_id,
  );
  const visibles = otros.slice(0, 4);
  const extra = otros.length - visibles.length;
  return (
    <header className="topbar isla">
      <div className="tb-grp">
        <div className="mark"><Logomark /></div>
        <span className="brand">la<b>idea</b></span>
        <span className="chev">›</span>
        {/* Capa 15: el breadcrumb muestra el EQUIPO actual (no el host). */}
        <span className="proy">{s.equipo ? s.equipo.nombre : s.proyecto}</span>
      </div>

      {visibles.length > 0 && (
        <>
          <span className="tb-div" />
          {/* OJO: .peers ya es el contenedor flex; NO sumar .tb-grp (su
              gap rompería el solapamiento por margin negativo de .av). */}
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
        </>
      )}

      <span className="spacer" />

      <div className="tb-grp">
        {/* Sólo el admin del equipo invita; el código aparece inline para
            copiarlo y pasarlo (un solo uso). */}
        {s.equipo?.rol === "admin" && (
          s.inviteCode ? (
            <span className="yo" title="código de un solo uso — compartilo">
              invitar <code>{s.inviteCode}</code>
            </span>
          ) : (
            <button className="invitar" onClick={crearInvite}>invitar</button>
          )
        )}
        <span className={clase}>{ETIQUETA[s.conn]}</span>
      </div>

      <span className="tb-div" />

      <div className="tb-grp">
        {s.yo && (
          <span className="yo">
            <span className="dot" style={{ background: s.yo.color }} />
            {s.yo.name}
          </span>
        )}
        {s.authed && <button className="salir" onClick={salir}>salir</button>}
      </div>
    </header>
  );
}
