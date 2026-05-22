// Pantalla de acceso — split: relato a la izquierda, consola a la derecha.
// Hasta capa 28 la consola tenía UN solo formulario con dos botones (Entrar
// + Crear cuenta). Para un usuario nuevo no estaba claro qué pasaba al
// pulsar uno u otro, y el formulario de registro NO pedía aceptar términos
// (legalmente débil y feo).
//
// Capa 29+: la consola ahora vive en dos vistas separadas — Login y
// Register — con un segmented control arriba y un link de footer para
// cruzarse de una a la otra. El panel izquierdo (pitch) NO cambia: es
// branding, sirve a ambas vistas. La acción de red sigue siendo la misma
// (`autenticar("login"|"register", …)`) — sólo cambia la UI.
//
// Register añade:
//   · campo "confirmar contraseña" con validación local (mismatch → error
//     inline, sin viaje al server),
//   · checkbox de aceptación con enlaces a dos modales (Términos y
//     Privacidad) que abren `LegalModal` — el envío queda gateado por
//     `aceptado=true` (no es un "submit y a ver qué dice el server").
import { useEffect, useState } from "react";
import { useStore } from "../useStore";
import { autenticar } from "../store";
import { validarUsuarioNuevo } from "../validate";
import { useI18n, LangToggle } from "../i18n";
import { LegalModal, type LegalDoc } from "./LegalModal";
import { Logomark } from "./Logomark";
import { Github } from "lucide-react";

type Modo = "login" | "register";

export function Login() {
  const s = useStore();
  const { t } = useI18n();
  const [modo, setModo] = useState<Modo>("login");
  const [u, setU] = useState("");
  const [p, setP] = useState("");
  const [p2, setP2] = useState("");
  const [aceptado, setAceptado] = useState(false);
  const [busy, setBusy] = useState(false);
  // Error local del formulario (validación que el server ni siquiera ve):
  // contraseñas no coinciden, contraseña corta, falta aceptar términos.
  // Si el server devuelve error vía `s.loginError`, se prioriza ese.
  const [localErr, setLocalErr] = useState<string>("");
  // Doc legal abierto (null = ningún modal). Cuando hay valor, se monta
  // <LegalModal/> por encima de toda la pantalla; cerrar = volver a null.
  const [legalOpen, setLegalOpen] = useState<LegalDoc | null>(null);
  // OAuth GitHub: si el callback falló, el navegador vuelve a
  // /app/?oauth_error=<código>. Guardamos el código crudo (no el texto) y
  // lo traducimos en el render, así el aviso sigue al idioma activo.
  const [oauthErrCode, setOauthErrCode] = useState<string>("");

  // El spinner se apaga cuando el server responde (auth ok = se cambia de
  // vista; auth fail = entra loginError). Si en 7s no llegó nada, lo
  // libero igual para que no quede colgado el botón.
  useEffect(() => { setBusy(false); }, [s.loginError, s.conn]);
  useEffect(() => {
    if (!busy) return;
    const id = setTimeout(() => setBusy(false), 7000);
    return () => clearTimeout(id);
  }, [busy]);

  // OAuth GitHub: al montar, leer una sola vez si volvimos con un error del
  // callback. Se limpia el query de la URL para que no quede en la barra ni
  // en el historial. El caso de éxito (?session=) lo absorbe `connect()` en
  // store.ts antes de que esta pantalla se monte.
  useEffect(() => {
    try {
      const params = new URLSearchParams(location.search);
      const err = params.get("oauth_error");
      if (!err) return;
      setOauthErrCode(err);
      params.delete("oauth_error");
      const q = params.toString();
      history.replaceState(
        null, "", location.pathname + (q ? "?" + q : "") + location.hash,
      );
    } catch { /* sin URL API: ignorar, se ve el login normal */ }
  }, []);

  // Al cambiar de modo limpio contraseñas y errores; el usuario se queda
  // (es la única cosa "estable" entre crear y entrar — la mayoría lo
  // recuerda y no quiere reescribirlo). El checkbox vuelve a falso porque
  // sólo aplica al registro y mezclar estados confunde.
  const cambiar = (nuevo: Modo) => {
    if (busy || nuevo === modo) return;
    setModo(nuevo);
    setP(""); setP2(""); setAceptado(false); setLocalErr("");
  };

  const offline = s.conn === "desconectado" || s.conn === "error";
  const usuarioVacio = !u.trim();
  const passVacio = !p;
  // Reglas mínimas locales antes de viajar al server. El server hará la
  // suya (los errores de capa 7), pero estas son las que ahorran un
  // round-trip y son inmediatamente entendibles.
  const passCorto = modo === "register" && p.length > 0 && p.length < 6;
  const passDistinto =
    modo === "register" && p2.length > 0 && p !== p2;
  // Validación de usuario EN VIVO al registrar — mismas reglas que el
  // backend (identity/store.py). Devuelve el código de error o null si OK;
  // lo mapeamos a i18n con la tabla MSG_USR. Para login NO validamos: cuentas
  // viejas pudieron registrarse con reglas distintas.
  const usuarioErr = modo === "register" && u.length > 0
    ? validarUsuarioNuevo(u) : null;
  const MSG_USR: Record<string, string> = {
    muy_corto: t.login_user_short,
    muy_largo: t.login_user_long,
    empieza_mal: t.login_user_starts,
    charset: t.login_user_charset,
    reservado: t.login_user_reserved,
  };
  // Códigos de error que devuelve el callback de OAuth GitHub. Se traduce
  // en el render (no al guardarlo) para que el aviso siga al idioma activo.
  const MSG_OAUTH: Record<string, string> = {
    cancelado: t.oauth_err_cancel,
    state: t.oauth_err_state,
    github: t.oauth_err_github,
  };
  const oauthErr = oauthErrCode
    ? (MSG_OAUTH[oauthErrCode] ?? t.oauth_err_generic)
    : "";

  const noPuede =
    busy ||
    usuarioVacio ||
    passVacio ||
    (modo === "register" && (
      !aceptado || p.length < 6 || p !== p2 || !!usuarioErr
    ));

  const enviar = () => {
    if (noPuede) return;
    // Re-chequeo defensivo para mensajes claros (el botón ya está
    // deshabilitado, pero por si alguien dispara Enter con estados raros).
    if (modo === "register") {
      if (p.length < 6) { setLocalErr(t.reg_pass_short); return; }
      if (p !== p2) { setLocalErr(t.reg_pass_mismatch); return; }
      if (!aceptado) { setLocalErr(t.reg_legal_required); return; }
    }
    setLocalErr("");
    setBusy(true);
    autenticar(modo, u.trim(), p);
  };

  const onEnter = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") enviar();
  };

  // OAuth GitHub: navegación de página entera al backend (contenedor `api`;
  // Caddy proxya /oauth/*). NO es fetch/WS. El backend hace el viaje a
  // GitHub y vuelve a /app/ con ?session= o ?oauth_error=.
  const irAGitHub = () => {
    window.location.href = "/oauth/github/login";
  };

  // Error a mostrar: si el server respondió algo, eso manda. Si no, el
  // local. Si no, el de offline. `min-height` en el CSS evita salto.
  const errVisible = s.loginError || localErr || oauthErr || (offline ? t.login_offline : "");

  return (
    <div className="landing">
      <section className="landing-pitch">
        <div className="lp-grid" aria-hidden />
        <div className="lp-inner">
          <div className="lp-marca">
            <Logomark size={28} className="lp-marca-mk" />
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
              <span className="who" style={{ background: "var(--info)" }}>A</span>
              Ana → roster.py <em className="ok">{t.login_feed_approved}</em>
            </div>
            <div className="lf-row">
              <span className="who" style={{ background: "var(--warn)" }}>K</span>
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
            <div className="lc-brand">
              <Logomark size={24} className="lc-brand-mk" />
              <b>Orux</b>
            </div>
            <div className="cue">
              <span className="lk" />{" "}
              {modo === "register" ? t.reg_session_cue : t.login_session_cue}
            </div>
          </div>

          {/* Segmented control — el cambio de vista es la decisión más
              visible del card. Acompaña al footer-link (los dos son
              redundantes a propósito: el segmented es para usuarios que
              "ven" la opción; el footer-link es para los que leen). */}
          <div className="lg-tabs" role="tablist" aria-label="modo de acceso">
            <button
              role="tab"
              aria-selected={modo === "login"}
              className={"lg-tab " + (modo === "login" ? "activo" : "")}
              onClick={() => cambiar("login")}
              disabled={busy}
            >
              {t.login_tab_signin}
            </button>
            <button
              role="tab"
              aria-selected={modo === "register"}
              className={"lg-tab " + (modo === "register" ? "activo" : "")}
              onClick={() => cambiar("register")}
              disabled={busy}
            >
              {t.login_tab_register}
            </button>
          </div>

          <p>{modo === "register" ? t.reg_desc : t.login_desc}</p>

          {/* Campos comunes: usuario + contraseña. En register se añade
              un segundo campo de contraseña y el bloque legal. */}
          <div className="fg">
            <label htmlFor="lg-u">
              {modo === "register" ? t.reg_user_label : t.login_user_label}
            </label>
            <input
              id="lg-u"
              placeholder={
                modo === "register" ? t.reg_user_placeholder : t.login_user_placeholder
              }
              autoComplete="username" autoFocus
              autoCapitalize="off" autoCorrect="off"
              spellCheck={false} maxLength={32}
              value={u} disabled={busy}
              aria-invalid={!!usuarioErr}
              aria-describedby={usuarioErr ? "lg-u-err" : "lg-u-hint"}
              onChange={(e) => setU(e.target.value)}
              onKeyDown={onEnter}
            />
            {/* En register: si lo que escribió rompe una regla, lo decimos
                EN VIVO; si todavía no escribió nada, mostramos la pista
                con el charset permitido (autodescriptivo, evita el "?". */}
            {modo === "register" && usuarioErr ? (
              <div id="lg-u-err" className="fg-hint err">
                {MSG_USR[usuarioErr] ?? t.login_user_charset}
              </div>
            ) : modo === "register" ? (
              <div id="lg-u-hint" className="fg-hint">
                {t.reg_user_hint}
              </div>
            ) : null}
          </div>
          <div className="fg">
            <label htmlFor="lg-p">
              {modo === "register" ? t.reg_pass_label : t.login_pass_label}
            </label>
            <input
              id="lg-p" type="password"
              placeholder={
                modo === "register" ? t.reg_pass_placeholder : t.login_pass_placeholder
              }
              autoComplete={modo === "register" ? "new-password" : "current-password"}
              maxLength={200}
              value={p} disabled={busy}
              onChange={(e) => setP(e.target.value)}
              onKeyDown={onEnter}
            />
            {passCorto && (
              <div className="fg-hint err">{t.reg_pass_short}</div>
            )}
          </div>

          {modo === "register" && (
            <div className="fg">
              <label htmlFor="lg-p2">{t.reg_pass2_label}</label>
              <input
                id="lg-p2" type="password"
                placeholder={t.reg_pass2_placeholder}
                autoComplete="new-password"
                maxLength={200}
                value={p2} disabled={busy}
                onChange={(e) => setP2(e.target.value)}
                onKeyDown={onEnter}
              />
              {passDistinto && (
                <div className="fg-hint err">{t.reg_pass_mismatch}</div>
              )}
            </div>
          )}

          {modo === "register" && (
            <label className="lg-legal">
              <input
                type="checkbox"
                checked={aceptado}
                disabled={busy}
                onChange={(e) => setAceptado(e.target.checked)}
              />
              <span>
                {t.reg_legal_pre}{" "}
                <button
                  type="button"
                  className="lazo-link"
                  onClick={() => setLegalOpen("terms")}
                  disabled={busy}
                >
                  {t.reg_legal_terms}
                </button>{" "}
                {t.reg_legal_and}{" "}
                <button
                  type="button"
                  className="lazo-link"
                  onClick={() => setLegalOpen("privacy")}
                  disabled={busy}
                >
                  {t.reg_legal_privacy}
                </button>
                {t.reg_legal_dot}
              </span>
            </label>
          )}

          {/* Acción primaria — un único botón (en vez de los dos antiguos).
              Su texto cambia según el modo activo. Eso elimina la duda de
              "¿este botón crea o entra?" que tenía la versión vieja. */}
          <div className="fila">
            <button
              className="primario" disabled={noPuede}
              onClick={enviar}
            >
              {busy ? (
                <>
                  <span className="spin" aria-hidden />
                  {modo === "register" ? t.reg_creating : t.login_verifying}
                </>
              ) : modo === "register" ? t.reg_submit : t.login_enter}
            </button>
          </div>

          <div className="err" role="alert">{errVisible}</div>

          {/* OAuth GitHub — entrar o registrarse con un clic, sin usuario
              ni contraseña. Navegación de página entera al backend (Caddy
              proxya /oauth/*); vuelve a /app/ con ?session= (lo absorbe
              store.ts) o ?oauth_error= (lo lee el useEffect de arriba).
              Sirve a ambos modos: si la cuenta gh: no existe, se crea. */}
          <div className="gh-sep" aria-hidden>
            <span className="gh-sep-line" />
            <span className="gh-sep-tx">{t.login_oauth_sep}</span>
            <span className="gh-sep-line" />
          </div>
          <button
            type="button"
            className="gh-btn"
            onClick={irAGitHub}
            disabled={busy}
          >
            <Github size={16} aria-hidden />
            {t.login_github}
          </button>

          {/* Footer-link al otro modo. Mismo motivo que el segmented: hay
              dos caminos al cruce porque hay dos formas de leer la UI. */}
          <div className="lg-cross">
            {modo === "login" ? (
              <>
                {t.login_to_register_pre}{" "}
                <button
                  type="button"
                  className="lazo-link"
                  onClick={() => cambiar("register")}
                  disabled={busy}
                >
                  {t.login_to_register_link}
                </button>
              </>
            ) : (
              <>
                {t.login_to_signin_pre}{" "}
                <button
                  type="button"
                  className="lazo-link"
                  onClick={() => cambiar("login")}
                  disabled={busy}
                >
                  {t.login_to_signin_link}
                </button>
              </>
            )}
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

      {legalOpen && (
        <LegalModal doc={legalOpen} onClose={() => setLegalOpen(null)} />
      )}
    </div>
  );
}
