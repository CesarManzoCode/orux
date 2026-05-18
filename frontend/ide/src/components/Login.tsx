import { useEffect, useState } from "react";
import { useStore } from "../useStore";
import { autenticar } from "../store";

// La app está CERRADA: sin autenticarse no se ve el workspace. Mismo
// contrato que siempre (capa 7); el server decide, esto sólo recoge
// usuario/contraseña.
//
// Dirección de arte v2 (login): deja de ser "una tarjeta flotando en
// negro". Es un split coherente con la landing — IZQUIERDA el relato en
// registro enterprise (kicker mono, titular sólido SIN gradiente, un
// readout sobrio de coordinación en vivo); DERECHA una CONSOLA de
// acceso: campos con label, cue de seguridad, botones precisos, estado
// de carga real y error elegante. El motion vive sólo acá (el IDE es
// quieto a propósito) y respeta prefers-reduced-motion (CSS global).
//
// El store NO expone "in-flight": al éxito el componente se desmonta
// (App: !authed → <Login/>); al fallo cambia loginError/conn. El estado
// `busy` se resetea ante esos cambios + un timeout de seguridad. No se
// toca el protocolo ni el store.
export function Login() {
  const s = useStore();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { setBusy(false); }, [s.loginError, s.conn]);
  useEffect(() => {
    if (!busy) return;
    const t = setTimeout(() => setBusy(false), 7000);
    return () => clearTimeout(t);
  }, [busy]);

  const offline = s.conn === "desconectado" || s.conn === "error";
  const vacio = !u.trim() || !p;

  const enviar = (tipo: "login" | "register") => {
    if (busy || vacio) return;
    setBusy(true);
    autenticar(tipo, u.trim(), p);
  };

  return (
    <div className="landing">
      {/* IZQUIERDA: el relato. Registro enterprise, no aurora. */}
      <section className="landing-pitch">
        <div className="lp-grid" aria-hidden />
        <div className="lp-inner">
          <div className="lp-marca">
            la<b>idea</b><span>coordination layer</span>
          </div>
          <div className="lp-eyebrow">
            <i /> capa de coordinación · sobre Git
          </div>
          <h1 className="lp-tag">
            Editás en equipo, en tiempo real.{" "}
            <span className="soft">Sin pisarte con nadie.</span>
          </h1>
          <p className="lp-tesis">
            Misma seguridad que branches, PRs y reviews — sin la
            ceremonia. El sistema sabe sin que nadie le pregunte.
          </p>

          <ul className="lp-points">
            <li><b>Presencia por línea.</b> Ves quién toca qué, en vivo.</li>
            <li><b>Impacto con resolución real.</b> Avisa qué se rompe antes de que se rompa.</li>
            <li><b>Sobre Git.</b> No lo reemplaza — <code>git clone</code> basta.</li>
          </ul>

          {/* Readout de coordinación en vivo — sobrio, no decorativo:
              dice "esto es multiplayer real", sin parpadear. */}
          <div className="lp-feed" aria-hidden>
            <div className="lf-h"><span className="lf-live" /> coordinación en vivo</div>
            <div className="lf-row">
              <span className="who" style={{ background: "#5fa8f5" }}>A</span>
              Ana → roster.py <em className="ok">propuesta aprobada</em>
            </div>
            <div className="lf-row">
              <span className="who" style={{ background: "#d9a441" }}>K</span>
              Kai → sync.py <em className="wt">impacto: 4 usos · avisado</em>
            </div>
          </div>
        </div>
      </section>

      {/* DERECHA: la consola de acceso. */}
      <section className="landing-auth">
        <div className="login-card">
          <div className="marca">la<b>idea</b></div>
          <div className="cue"><span className="lk" /> sesión cifrada · cuenta cerrada</div>
          <p>Entrá con tu usuario o creá uno nuevo. Sin cuenta no se ve el workspace.</p>

          <div className="fg">
            <label htmlFor="lg-u">Usuario</label>
            <input
              id="lg-u" placeholder="tu usuario" autoComplete="username" autoFocus
              value={u} disabled={busy}
              onChange={(e) => setU(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") enviar("login"); }}
            />
          </div>
          <div className="fg">
            <label htmlFor="lg-p">Contraseña</label>
            <input
              id="lg-p" type="password" placeholder="••••••••" autoComplete="current-password"
              value={p} disabled={busy}
              onChange={(e) => setP(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") enviar("login"); }}
            />
          </div>

          <div className="fila">
            <button
              className="primario" disabled={busy || vacio}
              onClick={() => enviar("login")}
            >
              {busy ? <><span className="spin" aria-hidden />Verificando…</> : "Entrar"}
            </button>
            <button
              className="secundario" disabled={busy || vacio}
              onClick={() => enviar("register")}
            >
              Crear cuenta
            </button>
          </div>

          <div className="err" role="alert">
            {s.loginError || (offline ? "Sin conexión con el servidor — reintentá." : "")}
          </div>
          <div className="cardfoot">
            Tu sesión viaja cifrada. El workspace es un repo Git real.
          </div>
        </div>
      </section>
    </div>
  );
}
