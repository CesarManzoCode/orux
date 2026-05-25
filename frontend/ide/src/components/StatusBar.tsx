import { useStore } from "../useStore";
import { chipDe } from "../lang";
import { useI18n } from "../i18n";

// StatusBar — fila inferior. Antes mostraba SOLO `git_status` (el estado
// del repo en el server). El testing real encontró el gap: el usuario
// teclea y ve "limpio" porque el repo aún no tiene esos cambios, lo que
// rompe la confianza ("¿se guardó o no?"). Ahora cruzamos las dos
// verdades:
//  - rama / cambios del repo (git status del server) -> el lado "vault"
//  - sin marcar / borradores (local, capa 19/28) -> el lado "tu trabajo"
// El usuario ve los dos. Si todo está sincronizado, sin ruido; si hay
// drafts sin enviar o sin marcar, lo dice claro.
export function StatusBar() {
  const s = useStore();
  const { t } = useI18n();
  const g = s.git;
  const enLinea = Object.keys(s.peers).length + (s.yo ? 1 : 0);
  const propsParaMi = Object.values(s.proposals).filter(
    (p) => s.yo && s.owners[p.path] === s.yo.client_id,
  ).length;
  const lang = s.currentPath ? chipDe(s.currentPath).nom : "—";
  // Conteos locales. `dirty` = archivos editados desde el último Ctrl+S;
  // `drafts` = subset de dirty donde NO soy dueño, así que aún no viajó
  // al server. Mostramos drafts con prioridad (pérdida potencial real) y
  // los "sin marcar" del dueño en segundo plano (no es pérdida, solo
  // análisis pendiente).
  const draftPaths = Object.keys(s.drafts);
  const nDrafts = draftPaths.length;
  const nDirty = Object.values(s.dirty).filter(Boolean).length;
  const nSinMarcarSinDraft = Math.max(0, nDirty - nDrafts);
  // Tooltip enriquecido para el segmento drafts: el conteo solo no
  // basta — al usuario le sirve recordar QUÉ archivos quedaron con
  // propuesta local. Mostramos hasta 3 paths (los más representativos)
  // + un "…" cuando hay más. Si hay solo uno, el listado lo sustituye
  // por la explicación del título (más conciso). El tooltip nativo
  // junta título + paths con saltos de línea, que la mayoría de
  // navegadores respeta.
  const draftsTitle = nDrafts > 0
    ? (nDrafts <= 3
        ? t.stb_drafts_title + "\n" + draftPaths.join("\n")
        : t.stb_drafts_title + "\n" +
          draftPaths.slice(0, 3).join("\n") +
          "\n… +" + (nDrafts - 3))
    : t.stb_drafts_title;

  const CONN: Record<string, string> = {
    conectando: t.stb_connecting,
    conectado: t.stb_online,
    desconectado: t.stb_offline,
    error: t.stb_error,
  };

  const connClase =
    s.conn === "conectado" ? "ok" : s.conn === "conectando" ? "" : "bad";

  return (
    <footer className="statusbar isla">
      <span className={"sb conn " + connClase}>
        <span className="sb-led" />
        {CONN[s.conn] ?? CONN.conectando}
      </span>
      <span className="sb-div" />
      <span className="sb">
        ⎇ <b>{g && g.available ? (g.branch || "—") : t.stb_no_git}</b>
      </span>
      {g && g.available && (
        <>
          <span className="sb-div" />
          <span
            className={"sb" + (g.changes ? " acc-warn" : "")}
            title={t.tb_changes_title}
          >
            {g.changes === 0
              ? t.stb_clean
              : g.changes + " " + (g.changes === 1 ? t.stb_change : t.stb_changes)}
          </span>
        </>
      )}
      {/* Drafts = pérdida potencial si se cierra el navegador (cambios
          locales que aún no salieron al server). Color de alerta y
          tooltip explicativo. */}
      {nDrafts > 0 && (
        <>
          <span className="sb-div" />
          <span className="sb acc-warn" title={draftsTitle}>
            {nDrafts} {nDrafts === 1 ? t.stb_drafts : t.stb_drafts_pl}
          </span>
        </>
      )}
      {/* "Sin marcar" del dueño: ya viajó el contenido, solo falta Ctrl+S
          para que el server corra el análisis de impacto. No es pérdida —
          señal de "tareita pendiente", color neutro. */}
      {nSinMarcarSinDraft > 0 && (
        <>
          <span className="sb-div" />
          <span className="sb acc-info" title={t.stb_unmarked_title}>
            {nSinMarcarSinDraft} {t.stb_unmarked}
          </span>
        </>
      )}
      {propsParaMi > 0 && (
        <>
          <span className="sb-div" />
          <span className="sb acc-info" title={t.stb_to_review_title}>
            {propsParaMi} {t.stb_to_review}
          </span>
        </>
      )}

      <span className="spacer" />

      <span className="sb">
        <span className="sb-live" /> {enLinea} {t.stb_online_label}
      </span>
      <span className="sb-div" />
      <span className="sb">{lang}</span>
      {s.currentPath && (
        <>
          {/* Ln/Col + Spaces: prescindibles en pantallas medianas — la
              info ya vive en el editor (cursor visible). Marcamos con
              `sb-low` para que el CSS los esconda <=1080px sin tocar
              la jerarquía de la izquierda (conn/branch/drafts). */}
          <span className="sb-div sb-div-low" />
          <span className="sb tabnum sb-low">
            Ln {s.caret.line}, Col {s.caret.col}
          </span>
          <span className="sb-div sb-div-low" />
          <span className="sb sb-low">{t.stb_spaces}</span>
        </>
      )}
      <span className="sb-div" />
      <span className="sb">
        {s.yo && <span className="sb-pt" style={{ background: s.yo.color }} />}
        {s.yo ? s.yo.name : "—"}
      </span>
    </footer>
  );
}
