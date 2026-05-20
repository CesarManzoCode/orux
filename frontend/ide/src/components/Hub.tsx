import { useState } from "react";
import { useStore } from "../useStore";
import { crearEquipo, redimirInvite, seleccionarEquipo, salir } from "../store";

// Capa 15 v2 — HUB DASHBOARD. Autenticado pero todavía sin un equipo
// abierto. La app sigue cerrada un escalón más: hasta entrar a un
// equipo no se ve NADA (ni que otros equipos existen).
//
// 2026-05-19: la versión previa era el mismo split del Login con una
// tarjeta flotando a la derecha — no se sentía como "tu lugar", se
// sentía como otro login. El usuario lo pidió explícito: "un dashboard,
// un hub… literalmente su propio /hub y bien hecho para ir añadiendo
// cosas". Esta versión es eso:
//
//   ┌── header (marca · conexión · identidad · salir) ───────────────┐
//   │                                                                │
//   │  ┌── equipos (primario, grande) ──┐  ┌── identidad (KPIs) ──┐ │
//   │  │ lista de equipos seleccionable │  │ avatar / nombre / #s  │ │
//   │  └────────────────────────────────┘  └───────────────────────┘ │
//   │  ┌── acciones (crear / unirme) ─────┐ ┌── sistema · seguridad ┐│
//   │  │ form crear · form join           │ │ chips de garantías    ││
//   │  └──────────────────────────────────┘ └───────────────────────┘│
//   └────────────────────────────────────────────────────────────────┘
//
// El grid usa CSS Grid con áreas nombradas (.hub-grid). Sumar un widget
// nuevo = añadir un área y una tarjeta `.hub-card.hc-<algo>`, sin tocar
// el resto. El contrato del store es idéntico al de la Lobby vieja
// (crearEquipo / redimirInvite / seleccionarEquipo / salir, s.yo,
// s.equipos) — sólo cambió la presentación.
//
// El verde sigue reservado a "vivo" (.lp-feed .lf-live, .st-ok); los
// tonos de identidad son fríos/acero (capa Acero del login).

// Color estable por equipo: hash determinista del id → tono acotado
// legible sobre fondo oscuro. Mismo criterio que el color por usuario
// (capa 7), cliente-puro, sin deps.
function colorEquipo(seed: string): string {
  let h = 0;
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) | 0;
  return `hsl(${((h % 360) + 360) % 360} 42% 56%)`;
}

const CONN: Record<string, { txt: string; cls: string }> = {
  conectado: { txt: "sesión activa", cls: "ok" },
  conectando: { txt: "conectando…", cls: "wt" },
  desconectado: { txt: "sin conexión", cls: "bad" },
  error: { txt: "sin conexión", cls: "bad" },
};

export function Hub() {
  const s = useStore();
  const [nombre, setNombre] = useState("");
  const [code, setCode] = useState("");

  const yo = s.yo;
  const inicial = (yo?.name || "?").trim().charAt(0).toUpperCase() || "?";
  const nAdmin = s.equipos.filter((e) => e.rol === "admin").length;
  const conn = CONN[s.conn] || CONN.conectando;

  return (
    <div className="hub">
      {/* HEADER: marca + estado de conexión + identidad + salir. La barra
          superior fija que ancla "dónde estoy". Sin glow, registro
          enterprise — mismo lenguaje que la consola del Login. */}
      <header className="hub-head">
        <div className="hub-brand">
          <b>Orux</b>
          <span className="hub-brand-sub">coordination layer · hub</span>
        </div>
        <div className="hub-head-mid" aria-hidden>
          <span className={"hub-conn st-" + conn.cls}>
            <i /> {conn.txt}
          </span>
        </div>
        <div className="hub-me">
          <span
            className="hub-me-ava"
            style={{ background: yo?.color || "var(--accent)" }}
            aria-hidden
          >
            {inicial}
          </span>
          <span className="hub-me-meta">
            <b>{yo?.name || "—"}</b>
            <code>identidad estable</code>
          </span>
          <button className="hub-me-out" onClick={salir} title="salir de la cuenta">
            salir
          </button>
        </div>
      </header>

      {/* GRID de widgets. Áreas nombradas: cambiar la grid plantilla en
          CSS reordena/cambia tamaños sin tocar JSX. */}
      <main className="hub-grid">
        {/* EQUIPOS — primario, ocupa la columna grande. */}
        <section className="hub-card hc-teams" aria-label="tus equipos">
          <header className="hc-h">
            <span className="hc-h-eyebrow">tus equipos</span>
            <span className="hc-h-num">{s.equipos.length}</span>
            <span className="hc-h-hint">
              {s.equipos.length === 0
                ? "todavía vacío"
                : "elegí uno para abrir su workspace"}
            </span>
          </header>

          {s.equipos.length > 0 ? (
            <div className="hub-teams">
              {s.equipos.map((e) => (
                <button
                  key={e.id}
                  className="hub-team"
                  onClick={() => seleccionarEquipo(e.id)}
                >
                  <span
                    className="ht-ava"
                    style={{ background: colorEquipo(e.id) }}
                    aria-hidden
                  >
                    {(e.nombre || "?").trim().charAt(0).toUpperCase() || "?"}
                  </span>
                  <span className="ht-meta">
                    <span className="ht-name">{e.nombre}</span>
                    <span className="ht-rol">{e.rol}</span>
                  </span>
                  <span className="ht-go" aria-hidden>abrir →</span>
                </button>
              ))}
            </div>
          ) : (
            <div className="hub-empty">
              <b>Todavía no estás en ningún equipo.</b>
              <span>
                Creá uno (quedás admin) o unite con un código que te pasó un
                admin. Otro equipo no existe para vos hasta que estés dentro
                del tuyo.
              </span>
            </div>
          )}
        </section>

        {/* IDENTIDAD — readout de "vos como entidad estable", a la
            derecha arriba. KPIs duros, sin adjetivos. */}
        <section className="hub-card hc-id" aria-label="tu identidad">
          <header className="hc-h">
            <span className="hc-h-eyebrow">tu identidad</span>
          </header>
          <div className="hc-id-row">
            <span
              className="hc-id-ava"
              style={{ background: yo?.color || "var(--accent)" }}
              aria-hidden
            >
              {inicial}
            </span>
            <div className="hc-id-meta">
              <b>{yo?.name || "—"}</b>
              <code>{yo?.color || "—"}</code>
            </div>
          </div>
          <div className="hc-id-kpis">
            <div>
              <b>{s.equipos.length}</b>
              <span>equipo{s.equipos.length === 1 ? "" : "s"}</span>
            </div>
            <div>
              <b>{nAdmin}</b>
              <span>como admin</span>
            </div>
          </div>
          <p className="hc-id-foot">
            Tu identidad sobrevive a reconectar — el sistema sabe quién sos
            sin que lo digas.
          </p>
        </section>

        {/* ACCIONES — crear equipo / unirme con código. Una tarjeta,
            dos formularios separados por un hairline. */}
        <section className="hub-card hc-new" aria-label="crear o unirme">
          <header className="hc-h">
            <span className="hc-h-eyebrow">crear o unirme</span>
          </header>

          <div className="fg">
            <label htmlFor="hb-new">Crear un equipo</label>
            <div className="hub-row">
              <input
                id="hb-new"
                placeholder="nombre del equipo"
                value={nombre}
                onChange={(e) => setNombre(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && nombre.trim()) crearEquipo(nombre.trim());
                }}
              />
              <button
                className="primario"
                disabled={!nombre.trim()}
                onClick={() => { if (nombre.trim()) crearEquipo(nombre.trim()); }}
              >
                crear
              </button>
            </div>
            <p className="fg-hint">Quedás admin del equipo que creás.</p>
          </div>

          <div className="hub-sep" />

          <div className="fg">
            <label htmlFor="hb-code">Unirme con un código</label>
            <div className="hub-row">
              <input
                id="hb-code"
                placeholder="código de invitación"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && code.trim()) redimirInvite(code.trim());
                }}
              />
              <button
                className="secundario"
                disabled={!code.trim()}
                onClick={() => { if (code.trim()) redimirInvite(code.trim()); }}
              >
                unirme
              </button>
            </div>
            <p className="fg-hint">El admin del equipo te pasó el código.</p>
          </div>

          <div className="err" role="alert">{s.equipoError || ""}</div>
        </section>

        {/* SISTEMA — banda de garantías técnicas, mismo idioma que el
            seclist del Login. Espacio reservado para sumar status (en
            cola de futuras capas: invites pendientes, último push,
            telemetría, etc.). */}
        <section className="hub-card hc-sys" aria-label="sistema">
          <header className="hc-h">
            <span className="hc-h-eyebrow">sistema</span>
          </header>
          <div className="hc-sys-list">
            <div className="hc-sys-row">
              <i className="hc-dot ok" /> sesión <b>HMAC</b>
              <span>el token se firma localmente, no viaja en claro</span>
            </div>
            <div className="hc-sys-row">
              <i className="hc-dot ok" /> identidad <b>estable</b>
              <span>el mismo punto que te representa en todos tus equipos</span>
            </div>
            <div className="hc-sys-row">
              <i className="hc-dot ok" /> sin <b>telemetría</b>
              <span>orux no te observa; el workspace es un repo Git real</span>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
