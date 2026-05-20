import { useStore } from "../useStore";
import { resolver, seleccionar, descartarImpacto, nombreDe } from "../store";
import { diffLineas } from "../lang";
import { useI18n } from "../i18n";

function Propuestas() {
  const s = useStore();
  const { t } = useI18n();
  const mias = Object.values(s.proposals).filter(
    (p) => s.yo && s.owners[p.path] === s.yo.client_id
  );
  if (mias.length === 0) return null;
  return (
    <div className="tray">
      <h3>{t.tr_proposals} <span className="cuenta">{mias.length}</span></h3>
      {mias.map((p) => {
        const filas = diffLineas(s.files[p.path] ?? "", p.content);
        return (
          <div className="prop" key={p.id}>
            <div className="cab">
              <span className="quien">
                <b>{p.author_name}</b> {t.tr_proposes} <b>{p.path}</b>
              </span>
              <span className="acc">
                <button className="ok" onClick={() => resolver(p.id, true)}>{t.tr_approve}</button>
                <button className="no" onClick={() => resolver(p.id, false)}>{t.tr_reject}</button>
              </span>
            </div>
            <div className="diff">
              {filas.map((f, i) => (
                <div key={i} className={f.t}>{f.x || " "}</div>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

const _RANK: Record<string, number> = { alta: 3, media: 2, baja: 1 };
const _sev = (m: { severidades?: string[] }, i: number) =>
  (m.severidades && m.severidades[i]) || "media";

function Impactos() {
  const s = useStore();
  const { t } = useI18n();
  const lista = Object.entries(s.impacts).sort(([, a], [, b]) => {
    const mx = (m: typeof a) =>
      Math.max(0, ...m.symbols.map((_, i) => _RANK[_sev(m, i)] || 2));
    return mx(b) - mx(a);
  });
  if (lista.length === 0) return null;
  return (
    <div className="tray imp">
      <h3>{t.tr_impact} <span className="cuenta">{lista.length}</span></h3>
      {lista.map(([clave, m]) => (
        <div className="imp-row" key={clave}>
          <div className="izq">
            <span>
              <b>{m.author_name}</b> {t.tr_changed}{" "}
              {m.symbols.map((x, i) => (
                <span key={i}><code>{x}</code>{i < m.symbols.length - 1 ? ", " : ""}</span>
              ))}{" "}
              {t.tr_in} <b>{m.source_path}</b> {t.tr_affects} <b>{m.affected_path}</b>
            </span>
            {m.symbols.map((_, i) =>
              m.motivos[i] ? (
                <div className="por" key={i}>
                  <span className={"sev sev-" + _sev(m, i)}>
                    {t.tr_sev[_sev(m, i)] ?? _sev(m, i)}
                  </span>
                  <span className="motivo">{m.motivos[i]}</span>
                </div>
              ) : null
            )}
            {m.cadena && m.cadena.length > 1 && (
              <div className="cadena">
                {m.cadena.map((h, i) => (
                  <span key={i}>
                    {i > 0 && <span className="flecha"> → </span>}
                    <code>{h}</code>
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="acc">
            <button onClick={() => {
              if (m.affected_path in s.files) seleccionar(m.affected_path);
            }}>
              {t.tr_view(m.affected_path)}
            </button>
            <button onClick={() => descartarImpacto(clave)}>{t.tr_dismiss}</button>
          </div>
        </div>
      ))}
    </div>
  );
}

export function Trays() {
  return (<><Propuestas /><Impactos /></>);
}
