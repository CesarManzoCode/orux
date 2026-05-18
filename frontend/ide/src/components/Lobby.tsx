import { useState } from "react";
import { useStore } from "../useStore";
import { crearEquipo, redimirInvite, seleccionarEquipo, salir } from "../store";

// Capa 15: autenticado pero todavía sin equipo. La app sigue cerrada un
// escalón más: hasta entrar a un equipo no se ve NADA (ni que otros
// equipos existen). Acá: elegir uno de los míos, crear uno nuevo (quedo
// admin), o unirme con un código que me pasó un admin.
export function Lobby() {
  const s = useStore();
  const [nombre, setNombre] = useState("");
  const [code, setCode] = useState("");

  // Reusa el patrón .login-card (misma tarjeta que el login) y los
  // patrones de botón del sistema (.primario/.secundario/.lazo) en vez
  // de estilos inline sueltos: una sola fuente de verdad visual.
  return (
    <div className="login">
      <div className="login-card" style={{ width: "min(420px, 100%)" }}>
        <div className="marca">la<b>idea</b></div>
        <p>
          Hola <b>{s.yo?.name}</b>. Para entrar necesitás un equipo. Otro
          equipo no existe para vos hasta que estés dentro del tuyo.
        </p>

        {s.equipos.length > 0 && (
          <>
            <div className="h2" style={{ marginTop: 4 }}>
              tus equipos <span className="h2-num">{s.equipos.length}</span>
            </div>
            {s.equipos.map((e) => (
              <button
                key={e.id}
                className="btn-nuevo"
                onClick={() => seleccionarEquipo(e.id)}
              >
                <span style={{ flex: 1 }}>{e.nombre}</span>
                <span style={{ color: "var(--faint)" }}>· {e.rol}</span>
              </button>
            ))}
          </>
        )}

        <div className="h2" style={{ marginTop: 8 }}>crear un equipo</div>
        <input
          placeholder="nombre del equipo"
          value={nombre}
          onChange={(e) => setNombre(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && nombre.trim()) crearEquipo(nombre.trim()); }}
        />
        <button
          className="primario"
          onClick={() => { if (nombre.trim()) crearEquipo(nombre.trim()); }}
        >
          crear (seré admin)
        </button>

        <div className="h2" style={{ marginTop: 8 }}>unirme con un código</div>
        <input
          placeholder="código de invitación"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter" && code.trim()) redimirInvite(code.trim()); }}
        />
        <button
          className="secundario"
          onClick={() => { if (code.trim()) redimirInvite(code.trim()); }}
        >
          unirme
        </button>

        {s.equipoError && <div className="err">{s.equipoError}</div>}
        <button className="lazo" onClick={salir}>salir</button>
      </div>
    </div>
  );
}
