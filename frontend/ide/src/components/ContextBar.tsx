import { useStore } from "../useStore";
import { reclamar, nombreDe } from "../store";

// Barra de contexto del archivo abierto: quién más está acá, el dueño y
// (si no tiene) reclamar. La cara visible de la tesis: tocás algo ajeno ->
// se negocia.
export function ContextBar() {
  const s = useStore();
  const path = s.currentPath;
  if (!path) return <div className="ctxbar" />;

  const aqui = Object.values(s.peers).filter(
    (p) => p.path === path && (!s.yo || p.client_id !== s.yo.client_id)
  );
  const due = s.owners[path];
  const esMio = s.yo && due === s.yo.client_id;

  return (
    <div className="ctxbar">
      <span className="aqui">
        {aqui.map((p) => (
          <span key={p.client_id} className="quien" style={{ background: p.color }}>
            {p.name} · {p.line}
          </span>
        ))}
      </span>
      {!due ? (
        <button className="reclamar" onClick={() => reclamar(path)}>reclamar este archivo</button>
      ) : esMio ? (
        <span className="otag tuyo">tuyo</span>
      ) : (
        <>
          <span className="otag ajeno">de {nombreDe(due)}</span>
          <span className="ctx-nota">
            lo que escribas se le propone a {nombreDe(due)} — no se aplica hasta que apruebe
          </span>
        </>
      )}
    </div>
  );
}
