import { useEffect, useState } from "react";
import { useStore } from "../useStore";
import { autenticar } from "../store";
import { useI18n, LangToggle } from "../i18n";

export function Login() {
  const s = useStore();
  const { t } = useI18n();
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { setBusy(false); }, [s.loginError, s.conn]);
  useEffect(() => {
    if (!busy) return;
    const id = setTimeout(() => setBusy(false), 7000);
    return () => clearTimeout(id);
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
      <section className="landing-pitch">
        <div className="lp-grid" aria-hidden />
        <div className="lp-inner">
          <div className="lp-marca">
            <b>Orux</b><span>{t.login_eyebrow.split("·")[0].trim()}</span>
          </div>
          <div className="lp-eyebrow">
            <i /> {t.login_eyebrow}
          </div>
          <h1 className="lp-tag">
            {t.login_pitch_title1}{" "}
            <span className="soft">{t.login_pitch_title2}</span>
          </h1>
          <p className="lp-tesis">{t.login_pitch_desc}</p>

          <ul className="lp-points">
            <li><b>{t.login_li1_b}</b>{t.login_li1}</li>
            <li><b>{t.login_li2_b}</b>{t.login_li2}</li>
            <li>
              <b>{t.login_li3_b}</b>{t.login_li3}
              <code>git clone</code>{t.login_li3_post}
            </li>
          </ul>

          <div className="lp-feed" aria-hidden>
            <div className="lf-h"><span className="lf-live" /> {t.login_feed_header}</div>
            <div className="lf-row">
              <span className="who" style={{ background: "#6ea8e6" }}>A</span>
              Ana → roster.py <em className="ok">{t.login_feed_approved}</em>
            </div>
            <div className="lf-row">
              <span className="who" style={{ background: "#d6a341" }}>K</span>
              Kai → sync.py <em className="wt">{t.login_feed_impact}</em>
            </div>
          </div>

          <div className="lp-sys" aria-hidden>
            <span>{t.login_sys_git_pre} <b>Git</b></span>
            <span>{t.login_sys_pres_pre} <b>{t.login_sys_pres_val}</b></span>
            <span>{t.login_sys_prev_pre} <b>{t.login_sys_prev_val}</b>{t.login_sys_prev_post}</span>
          </div>
        </div>
      </section>

      <section className="landing-auth">
        <div className="login-card">
          <div className="lc-head">
            <div className="lc-brand"><b>Orux</b></div>
            <div className="cue"><span className="lk" /> {t.login_session_cue}</div>
          </div>
          <p>{t.login_desc}</p>

          <div className="fg">
            <label htmlFor="lg-u">{t.login_user_label}</label>
            <input
              id="lg-u" placeholder={t.login_user_placeholder}
              autoComplete="username" autoFocus
              autoCapitalize="off" autoCorrect="off"
              spellCheck={false} maxLength={32}
              value={u} disabled={busy}
              onChange={(e) => setU(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") enviar("login"); }}
            />
          </div>
          <div className="fg">
            <label htmlFor="lg-p">{t.login_pass_label}</label>
            <input
              id="lg-p" type="password"
              placeholder={t.login_pass_placeholder}
              autoComplete="current-password"
              maxLength={200}
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
              {busy
                ? <><span className="spin" aria-hidden />{t.login_verifying}</>
                : t.login_enter}
            </button>
            <button
              className="secundario" disabled={busy || vacio}
              onClick={() => enviar("register")}
            >
              {t.login_register}
            </button>
          </div>

          <div className="err" role="alert">
            {s.loginError || (offline ? t.login_offline : "")}
          </div>
          <div className="cardfoot">
            {t.login_foot.split("git clone")[0]}
            <code>git clone</code>
            {t.login_foot.split("git clone")[1]}
          </div>
          <div className="seclist" aria-hidden>
            <span>{t.login_sec1}</span>
            <span>{t.login_sec2}</span>
            <span>{t.login_sec3}</span>
          </div>

          <LangToggle className="login-lang" />
        </div>
      </section>
    </div>
  );
}
