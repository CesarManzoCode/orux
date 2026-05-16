import { useState } from "react";
import { useStore } from "../useStore";
import { autenticar } from "../store";

// La app está CERRADA: sin autenticarse no se ve el workspace. Mismo
// contrato que siempre (capa 7); el server decide, esto sólo recoge
// usuario/contraseña.
export function Login() {
  const s = useStore();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  return (
    <div className="login">
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
    </div>
  );
}
