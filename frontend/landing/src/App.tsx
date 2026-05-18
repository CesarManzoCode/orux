import { useEffect, useState, type ReactNode } from "react";
import { motion, useReducedMotion, type Variants } from "framer-motion";

/* Landing de laidea — dirección de arte v3 "Infraestructura / Sala de
   control". No es una landing SaaS: es la ficha de una capa de
   coordinación para equipos de ingeniería. Identidad ACERO (mate, sin
   gradiente de hue); el verde es estado "vivo", no marca. Composición
   asimétrica, escena de producto cinematográfica, copy honesto: producto
   real en producción, sin humo de "IA". Continuidad visual con el IDE. */

const APP = "/app"; // el IDE vive acá (capa 23b) — estos enlaces deben seguir

/* --- Motion: revelados mínimos y precisos. Se neutralizan vía
   prefers-reduced-motion (Framer + el bloque CSS). --- */
const fadeUp: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] } },
};
const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.08 } },
};

function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode;
  delay?: number;
  className?: string;
}) {
  return (
    <motion.div
      className={className}
      variants={fadeUp}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, amount: 0.4 }}
      transition={{ delay }}
    >
      {children}
    </motion.div>
  );
}

/* Cabecera de sección reutilizable: kicker mono + lead sólido. */
function Head({ k, children, sub }: { k: string; children: ReactNode; sub?: ReactNode }) {
  return (
    <>
      <Reveal><div className="kicker">{k}</div></Reveal>
      <Reveal delay={0.06}><h2 className="lead">{children}</h2></Reveal>
      {sub && <Reveal delay={0.1}><p className="sec-sub">{sub}</p></Reveal>}
    </>
  );
}

/* Marca con logomark de acero (rombo = nodo de coordinación). */
function Brand({ href = "#top", tag }: { href?: string; tag?: boolean }) {
  return (
    <a className="brand" href={href}>
      <span className="mk" aria-hidden />
      la<b>idea</b>
      {tag && <span className="tag">coordination layer</span>}
    </a>
  );
}

/* Los 3 tiempos del producto — el corazón de la tesis. */
const PASOS = [
  {
    n: "01",
    t: "Editás primero",
    d: "Abrís el archivo y escribís. Sin pedir permiso, sin esperar una rama. La presencia en vivo te muestra dónde está cada quien antes de pisarse.",
  },
  {
    n: "02",
    t: "Se negocia después",
    d: "Si tocás zona con dueño, tu cambio viaja como propuesta. El dueño la aprueba con un clic. El impacto avisa, solo, a quién depende de eso.",
  },
  {
    n: "03",
    t: "Se aplica al final",
    d: "Aprobado, se integra para todos en el acto. Commit y push siguen siendo Git de verdad: git clone basta para tener el proyecto completo.",
  },
];

const FLOW = [
  {
    n: "01 · PROPONE",
    t: "El cambio viaja como propuesta",
    d: "Tocás una zona con dueño y seguís editando. Tu cambio no se descarta ni te frena: queda en cola, atado al archivo y a vos.",
    chip: { txt: "diff listo · sin rama", cls: "" },
  },
  {
    n: "02 · RESUELVE",
    t: "El dueño decide con un clic",
    d: "Le llega la propuesta con el impacto ya calculado. Aprueba o pide ajuste. Sin reunión, sin PR, sin esperar al líder.",
    chip: { txt: "pendiente · 1 clic", cls: "wt" },
  },
  {
    n: "03 · APLICA",
    t: "Se integra para todo el equipo",
    d: "Aprobado, el cambio aparece en el editor de todos al instante y queda como commit Git real. Nadie quedó desincronizado.",
    chip: { txt: "aplicado · en Git", cls: "go" },
  },
];

const NOTS = [
  "No es governance corporativo, permisos ni vigilancia.",
  "No reemplaza Git, GitHub ni tu IDE: es una capa encima.",
  "No te bloquea antes de intentar — editar primero, siempre.",
  "No es un chatbot pegado a un editor.",
];

const FREE = [
  "Hasta 5 devs por equipo",
  "Coordinación completa: presencia, ownership, tentativo, Git",
  "Análisis de impacto con resolución real",
  "Un workspace por equipo · 2 lenguajes",
];
const PRO = [
  "Equipos grandes, multi-proyecto y organización",
  "Impacto transitivo y entre repos",
  "Conocimiento distribuido: el líder deja de ser cuello de botella",
  "Todos los lenguajes, análisis siempre tibio, integraciones",
];

/* Tira de métricas del sistema — registro enterprise, sustituye al
   slogan: datos, no adjetivos. */
const TRUST = [
  { k: "Modelo", v: <>Sobre <b>Git</b> · <i>git clone</i> basta</> },
  { k: "Conflictos", v: <>Se <b>previene</b>, no se fusiona · sin CRDT</> },
  { k: "Granularidad", v: <>Presencia <b>por línea</b>, no por archivo</> },
  { k: "Estado", v: <><i>en producción</i> · equipos reales</> },
];

/* Escena del producto del hero: evoca el IDE real (rail con ownership,
   editor con presencia, status bar) + tarjetas flotantes de impacto y
   propuesta. aria-hidden — vende continuidad y "sistema en marcha". */
function Stage() {
  return (
    <div className="stage" aria-hidden>
      <div className="stage-back2" />
      <div className="stage-back" />
      <div className="ide">
        <div className="ide-bar">
          <span className="tl r" /><span className="tl y" /><span className="tl g" />
          <span className="ide-path">workspace · <span className="br">main</span></span>
          <span className="ide-live">
            <span className="faces">
              <i className="face" style={{ background: "#43b98a" }}>T</i>
              <i className="face" style={{ background: "#6ea8e6" }}>A</i>
              <i className="face" style={{ background: "#d6a341" }}>K</i>
            </span>
            <span>4 en vivo</span>
          </span>
        </div>
        <div className="ide-body">
          <aside className="ide-rail">
            <div className="rail-h">core /</div>
            <span className="f on"><span className="dirn">›</span> roster.py <em className="own me">vos</em></span>
            <span className="f"><span className="dirn">›</span> sync.py <em className="own peer">Ana</em></span>
            <span className="f"><span className="dirn">›</span> impact.py</span>
            <span className="f"><span className="dirn">›</span> git.py</span>
            <div className="rail-h" style={{ marginTop: 12 }}>api /</div>
            <span className="f"><span className="dirn">›</span> routes.py</span>
          </aside>
          <div className="ide-code">
            <div className="ln"><span className="n">11</span><code><span className="kw">def</span> <span className="fn">claim</span>(path, user):</code></div>
            <div className="ln me"><span className="n">12</span><code>    owners[path] = user  <span className="cm"># vos</span></code></div>
            <div className="ln"><span className="n">13</span><code>    <span className="kw">return</span> Ownership(path)</code></div>
            <div className="ln"><span className="n">14</span><code></code></div>
            <div className="ln peer"><span className="n">15</span><code><span className="kw">def</span> <span className="fn">presence</span>(line):</code><span className="cursor">Ana</span></div>
            <div className="ln"><span className="n">16</span><code>    roster.touch(line)</code></div>
            <div className="ln"><span className="n">17</span><code>    broadcast(<span className="st">"presence"</span>)</code></div>
          </div>
        </div>
        <div className="ide-status">
          <span className="s acc"><span className="dotg" /> main</span>
          <span className="s">↑2 ↓0</span>
          <span className="s">4 en vivo</span>
          <span className="s acc">sin colisiones</span>
          <span className="s push">Python · UTF-8</span>
        </div>
      </div>

      <div className="float card-impact">
        <div className="ft"><span className="ic">▲</span> Análisis de impacto</div>
        <div className="body">
          Cambiar <code>claim()</code> afecta <b>4 usos reales</b> — resolución
          cruzada, no coincidencia de texto.
        </div>
        <div className="uses">
          <span>server/sync.py:142</span>
          <span>api/routes.py:88</span>
          <span>tests/test_own.py:23</span>
        </div>
        <div className="auto">Se avisó solo a quien depende de esto</div>
      </div>

      <div className="float card-prop">
        <div className="ft"><span className="ic">◇</span> Propuesta de Ana</div>
        <div className="meta">sync.py · <b>+12 −3</b> · impacto calculado</div>
        <div className="acts">
          <span className="ap">Aprobar</span>
          <span className="vw">Ver diff</span>
        </div>
        <div className="pend">pendiente · un clic la integra</div>
      </div>
    </div>
  );
}

export function App() {
  const reduce = useReducedMotion();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 16);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  const heroInit = reduce ? "show" : "hidden";

  return (
    <>
      <div className="grid-bg" aria-hidden />
      <div className="traces" aria-hidden />
      <div className="vignette" aria-hidden />

      <nav className={"nav" + (scrolled ? " scrolled" : "")}>
        <div className="wrap">
          <Brand tag />
          <div className="nav-links">
            <a href="#problema">El problema</a>
            <a href="#pilares">Qué hace</a>
            <a href="#como">Cómo funciona</a>
            <a href="#precio">Precio</a>
          </div>
          <div className="nav-right">
            <span className="nav-stat"><i />en producción</span>
            <span className="nav-sep" />
            <a className="btn ghost sm" href={APP}>
              Entrar <span className="arr">→</span>
            </a>
          </div>
        </div>
      </nav>

      {/* ── HERO ── */}
      <header className="hero" id="top">
        <div className="wrap">
          <motion.div
            className="hero-copy"
            variants={stagger}
            initial={heroInit}
            animate="show"
          >
            <motion.div variants={fadeUp}>
              <span className="eyebrow">
                <span className="live" /> En producción · equipos reales coordinando
              </span>
            </motion.div>
            <motion.h1 variants={fadeUp}>
              Tu equipo toca el código.{" "}
              <span className="dim">El sistema coordina el riesgo.</span>
            </motion.h1>
            <motion.p className="sub" variants={fadeUp}>
              Una capa de coordinación en tiempo real sobre Git, para equipos
              de 2 a 50. Ownership, presencia e impacto resueltos antes de que
              el cambio llegue a producción — sin la ceremonia de branches,
              PRs y reviews.
            </motion.p>
            <motion.div className="cta" variants={fadeUp}>
              <a className="btn primary lg" href={APP}>
                Entrar a laidea <span className="arr">→</span>
              </a>
              <a className="btn ghost lg" href="#como">Ver cómo funciona</a>
            </motion.div>
            <motion.div className="signals" variants={fadeUp}>
              <span className="sig">presencia · <b>por línea</b></span>
              <span className="sig">ownership · <b>invisible</b></span>
              <span className="sig">impacto · <b>resolución real</b></span>
            </motion.div>
          </motion.div>

          <motion.div
            initial={reduce ? { opacity: 1 } : { opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.85, delay: 0.25, ease: [0.22, 1, 0.36, 1] }}
          >
            <Stage />
          </motion.div>
        </div>
      </header>

      {/* ── Tira de métricas del sistema (estática, registro enterprise) ── */}
      <div className="trust">
        <div className="wrap">
          {TRUST.map((t) => (
            <div className="ti" key={t.k}>
              <span className="tk">{t.k}</span>
              <span className="tv">{t.v}</span>
            </div>
          ))}
        </div>
      </div>

      {/* ── EL RIESGO INVISIBLE (problema) ── */}
      <section id="problema">
        <span className="sec-line" />
        <div className="wrap">
          <Head
            k="01 · El problema"
            sub="Dos personas tocan archivos relacionados. Nadie lo ve. El conflicto y el cambio que rompe a un tercero aparecen al final, en el merge — cuando ya cuesta caro."
          >
            El riesgo no está en el código.{" "}
            <span className="soft">Está en que nadie lo ve a tiempo.</span>
          </Head>
          <Reveal delay={0.12}>
            <div className="risk">
              <div className="risk-col">
                <div className="risk-h">Ahora · sin coordinación</div>
                <div className="dev">
                  <span className="av" style={{ background: "#43b98a" }}>T</span>
                  <span className="nm">Vos · <em>roster.py</em></span>
                </div>
                <div className="dev">
                  <span className="av" style={{ background: "#6ea8e6" }}>A</span>
                  <span className="nm">Ana · <em>sync.py → usa claim()</em></span>
                </div>
              </div>
              <div className="risk-mid">
                <span className="file">claim()</span>
                <span className="clash">colisión latente</span>
              </div>
              <div className="risk-col">
                <div className="risk-h">Lo que Git ve</div>
                <div className="dev"><span className="nm" style={{ color: "var(--mut)" }}>commit local… push… </span></div>
                <div className="dev"><span className="nm" style={{ color: "var(--mut)" }}>rama… PR… review…</span></div>
              </div>
              <div className="risk-foot">
                <span className="x">!</span>
                <div>
                  Git no previene colisiones: las <b>descubre en el merge</b>.
                  Live Share no entiende tu código. Tu IDE no coordina al equipo.
                </div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── LO DETECTA SOLO (pilares como módulos) ── */}
      <section id="pilares">
        <span className="sec-line" />
        <div className="wrap">
          <Head
            k="02 · Qué hace, de verdad"
            sub="Tres mecanismos reales, funcionando hoy. Ninguno es humo: corren en producción con devs reales."
          >
            laidea lo detecta solo,{" "}
            <span className="soft">sin que nadie le pregunte.</span>
          </Head>
          <Reveal delay={0.12}>
            <div className="modules">
              {/* Presencia */}
              <div className="mod">
                <div className="mod-h">
                  <span className="d" style={{ background: "var(--live)" }} /> Presencia
                  <span className="ix">01 / 03</span>
                </div>
                <div className="mod-screen">
                  <div className="scr-pres">
                    <div className="pl x a"><span className="n">12</span><span className="bar" /><span className="who">T</span></div>
                    <div className="pl y b"><span className="n">15</span><span className="bar" /><span className="who">A</span></div>
                    <div className="pl"><span className="n">16</span><span className="bar" style={{ background: "var(--bg-3)" }} /></div>
                    <div className="pl y b"><span className="n">22</span><span className="bar" /><span className="who">A</span></div>
                  </div>
                </div>
                <div className="mod-cap">
                  <h3>Quién toca qué, en vivo</h3>
                  <p>Presencia por línea. Nunca dos en la misma: se previene antes, no se resuelve después.</p>
                </div>
              </div>

              {/* Ownership */}
              <div className="mod">
                <div className="mod-h">
                  <span className="d" style={{ background: "var(--peer)" }} /> Ownership
                  <span className="ix">02 / 03</span>
                </div>
                <div className="mod-screen">
                  <div className="scr-own">
                    <div className="row"><span className="fl">roster.py</span><span className="ar">→</span><span className="tg me">vos</span></div>
                    <div className="row"><span className="fl">sync.py</span><span className="ar">→</span><span className="tg pe">Ana</span></div>
                    <div className="row"><span className="fl">impact.py</span><span className="ar">→</span><span className="tg fr">libre</span></div>
                    <div className="row"><span className="fl">git.py</span><span className="ar">→</span><span className="tg pe">Kai</span></div>
                  </div>
                </div>
                <div className="mod-cap">
                  <h3>De quién es cada zona</h3>
                  <p>El sistema lo sabe sin que nadie pida permiso. Hay dueño: tu cambio se propone, no se bloquea.</p>
                </div>
              </div>

              {/* Impacto */}
              <div className="mod">
                <div className="mod-h">
                  <span className="d" style={{ background: "var(--risk)" }} /> Impacto
                  <span className="ix">03 / 03</span>
                </div>
                <div className="mod-screen">
                  <div className="scr-imp">
                    <div className="sig">
                      <code>claim(path)</code> <span className="chg">→ claim(path, user)</span>
                    </div>
                    <div className="u"><b>sync.py:142</b></div>
                    <div className="u"><b>routes.py:88</b></div>
                    <div className="u"><b>test_own.py:23</b></div>
                    <div className="ok">avisado automáticamente</div>
                  </div>
                </div>
                <div className="mod-cap">
                  <h3>Qué se rompe si cambiás esto</h3>
                  <p>Cambiás una firma y avisa, solo, a quién la usa de verdad. Resolución cruzada, sin falsos positivos.</p>
                </div>
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── COORDINA EN TIEMPO REAL (flujo) ── */}
      <section>
        <span className="sec-line" />
        <div className="wrap">
          <Head
            k="03 · Coordinación en tiempo real"
            sub="Lo que antes era rama → PR → review → merge, ahora es proponer → aprobar → aplicar. Mismo control, sin la ceremonia."
          >
            La negociación ocurre dentro del editor,{" "}
            <span className="soft">no en una cola de PRs.</span>
          </Head>
          <Reveal delay={0.12}>
            <div className="flow">
              {FLOW.map((f) => (
                <div className="fn" key={f.n}>
                  <div className="fn-n">{f.n}</div>
                  <h3>{f.t}</h3>
                  <p>{f.d}</p>
                  <span className={"chip " + f.chip.cls}>{f.chip.txt}</span>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </section>

      {/* ── MENOS CEREMONIA (3 tiempos) ── */}
      <section id="como">
        <span className="sec-line" />
        <div className="wrap">
          <Head
            k="04 · Cómo funciona"
            sub="La tesis, en tres tiempos. Misma seguridad que tu flujo actual; el sistema sabe sin que nadie le pregunte."
          >
            Editás primero. Se negocia después.{" "}
            <span className="soft">Se aplica al final.</span>
          </Head>
          <motion.div
            className="steps"
            variants={stagger}
            initial={reduce ? "show" : "hidden"}
            whileInView="show"
            viewport={{ once: true, amount: 0.2 }}
          >
            {PASOS.map((s) => (
              <motion.div key={s.n} className="step" variants={fadeUp}>
                <div className="step-n">{s.n}</div>
                <h3>{s.t}</h3>
                <p>{s.d}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── LO QUE NO SOMOS ── */}
      <section>
        <span className="sec-line" />
        <div className="wrap">
          <Head k="05 · Lo que NO somos">
            Vendemos coordinación,{" "}
            <span className="soft">no control.</span>
          </Head>
          <motion.div
            className="nots"
            variants={stagger}
            initial={reduce ? "show" : "hidden"}
            whileInView="show"
            viewport={{ once: true, amount: 0.3 }}
          >
            {NOTS.map((n) => (
              <motion.div className="not" key={n} variants={fadeUp}>
                <span>✕</span>
                <div>{n}</div>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* ── PRICING ── */}
      <section id="precio">
        <span className="sec-line" />
        <div className="wrap">
          <Head
            k="06 · Precio"
            sub="Gratis de verdad para empezar, sin asteriscos. Pagás cuando el equipo escala y necesita más profundidad."
          >
            Para equipos nuevos sin inercia,{" "}
            <span className="soft">empezar no cuesta.</span>
          </Head>
          <motion.div
            className="prices"
            variants={stagger}
            initial={reduce ? "show" : "hidden"}
            whileInView="show"
            viewport={{ once: true, amount: 0.2 }}
          >
            <motion.div className="price" variants={fadeUp}>
              <div className="tier">Free · para siempre</div>
              <h4>Tu equipo chico</h4>
              <p className="price-sub">Todo el core de coordinación, sin recortes. Para equipos que empiezan.</p>
              <ul>{FREE.map((f) => <li key={f}>{f}</li>)}</ul>
              <a className="btn ghost full" href={APP}>Empezar gratis</a>
            </motion.div>
            <motion.div className="price pro" variants={fadeUp}>
              <span className="badge">Recomendado al crecer</span>
              <div className="tier">Premium · escala y profundidad</div>
              <h4>Cuando crecés</h4>
              <p className="price-sub">Más equipo, más repos, análisis más profundo y conocimiento distribuido.</p>
              <ul>{PRO.map((f) => <li key={f}>{f}</li>)}</ul>
              <a className="btn primary full" href={APP}>Entrar a laidea <span className="arr">→</span></a>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* ── CTA FINAL ── */}
      <section className="final">
        <span className="sec-line" />
        <div className="wrap">
          <Reveal><h2>Misma vida, menos dolor.</h2></Reveal>
          <Reveal delay={0.06}>
            <p className="final-sub">
              Editar primero. Negociar después. Aplicar al final.
              El sistema sabe sin que nadie le pregunte.
            </p>
          </Reveal>
          <Reveal delay={0.12} className="final-cta">
            <a className="btn primary lg" href={APP}>Entrar a laidea <span className="arr">→</span></a>
            <a className="btn ghost lg" href="#como">Cómo funciona</a>
          </Reveal>
        </div>
      </section>

      <footer>
        <div className="wrap">
          <div className="foot-l">
            <Brand />
            <p>multiplayer semantic coding · misma vida, menos dolor</p>
          </div>
          <div className="foot-r">
            <a href={APP}>Entrar</a>
            <a href="#pilares">Qué hace</a>
            <a href="#como">Cómo funciona</a>
            <a href="#precio">Precio</a>
          </div>
        </div>
      </footer>
    </>
  );
}
