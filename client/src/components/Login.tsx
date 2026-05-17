import { useState } from "react";
import { useStore } from "../useStore";
import { autenticar } from "../store";

// La app está CERRADA: sin autenticarse no se ve el workspace. Mismo
// contrato que siempre (capa 7); el server decide, esto sólo recoge
// usuario/contraseña.
//
// Capa 25 (landing): antes era una tarjeta de 340px flotando en una
// página enorme y vacía — "espacio muerto". Ahora es un split: a la
// IZQUIERDA un panel con color de marca que CUENTA el producto (la
// tesis, el diferencial multiplayer) — llena el hueco con sentido, no
// con relleno; a la DERECHA el formulario sobre el negro frío. Dos
// áreas de color distintas = contraste real. Las animaciones (entrada,
// aurora ambiental, presencia que late) viven SÓLO acá: el IDE sigue
// quieto a propósito; la landing es lo único que tiene permiso de
// llamar la atención. Respeta prefers-reduced-motion (ver CSS).
export function Login() {
  const s = useStore();
  const [u, setU] = useState("");
  const [p, setP] = useState("");

  return (
    <div className="landing">
      {/* IZQUIERDA: el relato. Color de marca, no negro. */}
      <section className="landing-pitch">
        <div className="lp-aurora" aria-hidden />
        <div className="lp-inner">
          <div className="lp-marca">la<b>idea</b></div>
          <h1 className="lp-tag">
            Editá en equipo.<br />En tiempo real.<br />
            <span>Sin pisarte con nadie.</span>
          </h1>
          <p className="lp-tesis">
            Misma seguridad que branches, PRs y reviews — sin la
            ceremonia. El sistema sabe sin que nadie le pregunte.
          </p>

          <ul className="lp-puntos">
            <li style={{ animationDelay: "0.18s" }}>
              <b>Presencia en vivo.</b> Ves quién toca qué, línea por línea.
            </li>
            <li style={{ animationDelay: "0.26s" }}>
              <b>Impacto semántico.</b> Te avisa qué se rompe antes de que se rompa.
            </li>
            <li style={{ animationDelay: "0.34s" }}>
              <b>Sobre Git.</b> No lo reemplaza. <code>git clone</code> basta.
            </li>
          </ul>

          {/* Demostración muda del diferencial: tres presentes que
              laten. No es decoración: es "esto es multiplayer". */}
          <div className="lp-presencia" aria-hidden>
            <span className="pp" style={{ background: "#4cc38a" }}>A</span>
            <span className="pp" style={{ background: "#6cb6ff" }}>M</span>
            <span className="pp" style={{ background: "#e3b341" }}>K</span>
            <span className="pp-txt">3 editando ahora</span>
          </div>
        </div>
      </section>

      {/* DERECHA: la compuerta. */}
      <section className="landing-auth">
        <div className="login-card">
          <div className="marca">la<b>idea</b></div>
          <p>Entrá con tu usuario o creá uno nuevo. La app está cerrada: sin cuenta no se ve el workspace.</p>
          <input
            placeholder="usuario" autoComplete="username" autoFocus
            value={u} onChange={(e) => setU(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") autenticar("login", u, p); }}
          />
          <input
            type="password" placeholder="contraseña" autoComplete="current-password"
            value={p} onChange={(e) => setP(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") autenticar("login", u, p); }}
          />
          <div className="fila">
            <button className="primario" onClick={() => autenticar("login", u, p)}>entrar</button>
            <button className="secundario" onClick={() => autenticar("register", u, p)}>crear cuenta</button>
          </div>
          <div className="err">{s.loginError || ""}</div>
        </div>
      </section>
    </div>
  );
}
