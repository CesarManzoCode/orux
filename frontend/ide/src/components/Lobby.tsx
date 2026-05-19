import { useState } from "react";
import { useStore } from "../useStore";
import { crearEquipo, redimirInvite, seleccionarEquipo, salir } from "../store";

// Capa 15: autenticado pero todavía sin un equipo abierto. La app sigue
// cerrada un escalón más: hasta entrar a un equipo no se ve NADA (ni que
// otros equipos existen). Esto es el HUB. No es una tarjeta flotando en
// negro: es el MISMO split full-bleed que el Login (relato/identidad a la
// izquierda, consola accionable a la derecha) — coherente y de grado
// producción. El contrato del store es idéntico (crearEquipo /
// redimirInvite / seleccionarEquipo / salir, s.yo, s.equipos); sólo
// cambió la presentación. Reusa el sistema Acero (.landing/.landing-pitch
// /.landing-auth/.lp-*) ya validado en el Login.

// Color estable por equipo (identidad, no estado): hash determinista del
// id → un tono acotado que se lee sobre fondo oscuro. Mismo criterio que
// el color por usuario (capa 7), cliente-puro, sin deps. El verde sigue
// reservado a "vivo": estos tonos son de identidad, apagados a propósito.
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

export function Lobby() {
  const s = useStore();
  const [nombre, setNombre] = useState("");
  const [code, setCode] = useState("");

  const yo = s.yo;
  const inicial = (yo?.name || "?").trim().charAt(0).toUpperCase() || "?";
  const nAdmin = s.equipos.filter((e) => e.rol === "admin").length;
  const conn = CONN[s.conn] || CONN.conectando;

  return (
    <div className="landing">
      {/* IZQUIERDA: tu identidad. Cinematográfica, registro enterprise,
          plano técnico (mismo lienzo que el relato del Login). */}
      <section className="landing-pitch">
        <div className="lp-grid" aria-hidden />
        <div className="lp-inner">
          <div className="lp-marca">
            <b>Orux</b><span>coordination layer</span>
          </div>
          <div className="lp-eyebrow">
            <i className={"st-" + conn.cls} /> {conn.txt} · {yo?.name || "—"}
          </div>
          <h1 className="lp-tag">
            Hola, {yo?.name || "dev"}.{" "}
            <span className="soft">Elegí dónde coordinás.</span>
          </h1>
          <p className="lp-tesis">
            Otro equipo no existe para vos hasta que estés dentro del tuyo.
            Tu identidad es estable: el mismo punto que te representa, en
            cada equipo, en vivo.
          </p>

          {/* Tu cuenta como readout — instrumento, no adorno (mismo
              lenguaje que el feed de coordinación del Login). */}
          <div className="lp-feed" aria-label="tu cuenta">
            <div className="lf-h">
              <span className="lf-live" /> tu cuenta
            </div>
            <div className="hub-idrow">
              <span
                className="hub-ava"
                style={{ background: yo?.color || "var(--accent)" }}
                aria-hidden
              >
                {inicial}
              </span>
              <div className="hub-idmeta">
                <b>{yo?.name || "—"}</b>
                <code>identidad {yo?.color || "—"}</code>
              </div>
            </div>
            <div className="hub-kpis">
              <div>
                <b>{s.equipos.length}</b>
                <span>equipo{s.equipos.length === 1 ? "" : "s"}</span>
              </div>
              <div>
                <b>{nAdmin}</b>
                <span>como admin</span>
              </div>
            </div>
          </div>

          <div className="lp-sys" aria-hidden>
            <span>sobre <b>Git</b></span>
            <span>presencia <b>por línea</b></span>
            <span>se <b>previene</b>, no se fusiona</span>
          </div>
        </div>
      </section>

      {/* DERECHA: la consola. Entrar a un equipo, crear, o unirme. */}
      <section className="landing-auth">
        <div className="login-card">
          <div className="marca"><b>Orux</b></div>
          <div className="cue"><span className="lk" /> cuenta cerrada · elegí tu equipo</div>

          <div className="h2" style={{ marginTop: "0.7rem" }}>
            tus equipos <span className="h2-num">{s.equipos.length}</span>
          </div>

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
              Todavía no estás en ningún equipo. Creá uno (quedás admin) o
              unite con un código que te pasó un admin.
            </div>
          )}

          <div className="hub-sep" />

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
          </div>

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
          </div>

          <div className="err" role="alert">{s.equipoError || ""}</div>

          <div className="cardfoot">
            Sesión cifrada. Tu identidad y tu ownership sobreviven a
            reconectar — el sistema sabe quién sos sin que lo digas.
          </div>
          <div className="hub-foot">
            <div className="seclist" aria-hidden>
              <span>sesión HMAC</span>
              <span>identidad estable</span>
            </div>
            <button className="lazo" onClick={salir}>salir de la cuenta</button>
          </div>
        </div>
      </section>
    </div>
  );
}
