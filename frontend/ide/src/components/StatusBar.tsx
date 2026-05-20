import { useStore } from "../useStore";
import { chipDe } from "../lang";
import { useI18n } from "../i18n";

export function StatusBar() {
  const s = useStore();
  const { t } = useI18n();
  const g = s.git;
  const enLinea = Object.keys(s.peers).length + (s.yo ? 1 : 0);
  const propsParaMi = Object.values(s.proposals).filter(
    (p) => s.yo && s.owners[p.path] === s.yo.client_id,
  ).length;
  const lang = s.currentPath ? chipDe(s.currentPath).nom : "—";

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
          <span className={"sb" + (g.changes ? " acc-warn" : "")}>
            {g.changes === 0
              ? t.stb_clean
              : g.changes + " " + (g.changes === 1 ? t.stb_change : t.stb_changes)}
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
          <span className="sb-div" />
          <span className="sb tabnum">
            Ln {s.caret.line}, Col {s.caret.col}
          </span>
          <span className="sb-div" />
          <span className="sb">{t.stb_spaces}</span>
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
