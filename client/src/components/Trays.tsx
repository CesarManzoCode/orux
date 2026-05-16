import { useStore } from "../useStore";
import { resolver, seleccionar, descartarImpacto, nombreDe } from "../store";
import { diffLineas } from "../lang";

// Bandeja del dueño: propuestas que esperan su verde/rojo. Diff por líneas.
function Propuestas() {
  const s = useStore();
  // Sólo las de archivos que YO poseo (el server ya las dirige al dueño,
  // esto es defensa: si solté ownership dejan de mostrarse).
  const mias = Object.values(s.proposals).filter(
    (p) => s.yo && s.owners[p.path] === s.yo.client_id
  );
  if (mias.length === 0) return null;
  return (
    <div className="tray">
      <h3>propuestas para vos ({mias.length})</h3>
      {mias.map((p) => {
        const filas = diffLineas(s.files[p.path] ?? "", p.content);
        return (
          <div className="prop" key={p.id}>
            <div className="cab">
              <span className="quien">
                <b>{p.author_name}</b> propone cambios a <b>{p.path}</b>
              </span>
              <span className="acc">
                <button className="ok" onClick={() => resolver(p.id, true)}>aprobar</button>
                <button className="no" onClick={() => resolver(p.id, false)}>rechazar</button>
              </span>
            </div>
            <div className="diff">
              {filas.map((f, i) => (
                <div key={i} className={f.t}>
                  {(f.t === "add" ? "+ " : f.t === "del" ? "- " : "  ") + f.x}
                </div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Avisos de impacto: "cambiaron algo que tu archivo usa" + POR QUÉ (lo que
// lo volvió aviso real y no adorno).
function Impactos() {
  const s = useStore();
  const lista = Object.entries(s.impacts);
  if (lista.length === 0) return null;
  return (
    <div className="tray imp">
      <h3>impacto en tus archivos ({lista.length})</h3>
      {lista.map(([clave, m]) => (
        <div className="imp-row" key={clave}>
          <div className="izq">
            <span>
              <b>{m.author_name}</b> cambió{" "}
              {m.symbols.map((x, i) => (
                <span key={i}><code>{x}</code>{i < m.symbols.length - 1 ? ", " : ""}</span>
              ))}{" "}
              en <b>{m.source_path}</b> — afecta tu <b>{m.affected_path}</b>
            </span>
            {m.symbols.map((_, i) =>
              m.motivos[i] ? (
                <div className="por" key={i}>↳ {m.motivos[i]}</div>
              ) : null
            )}
          </div>
          <div className="acc">
            <button onClick={() => { if (m.affected_path in s.files) seleccionar(m.affected_path); }}>
              ver {m.affected_path}
            </button>
            <button onClick={() => descartarImpacto(clave)}>visto</button>
          </div>
        </div>
      ))}
    </div>
  );
}

export function Trays() {
  return (<><Propuestas /><Impactos /></>);
}
