import { useEffect, useState, type ReactNode } from "react";
import { motion, useReducedMotion, type Variants } from "framer-motion";

/* Landing de laidea — nivel premium, coherente con la identidad del IDE
   (continuidad landing→app). Mismo sistema de diseño que el editor: negros
   fríos, acento verde→cian, patrón "isla", motion orquestado. El copy es
   honesto: producto real en producción, sin humo de "IA". */

const APP = "/app"; // el IDE vive acá (capa 23b) — estos enlaces deben seguir

/* --- Motion: variantes base. Se neutralizan vía prefers-reduced-motion --- */
const fadeUp: Variants = {
  hidden: { opacity: 0, y: 26 },
  show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1] } },
};
const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.1 } },
};

/* Reveal: entrada al hacer scroll. Si el usuario pide menos movimiento,
   Framer (useReducedMotion) hace que las variantes no desplacen nada. */
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
      viewport={{ once: true, amount: 0.35 }}
      transition={{ delay }}
    >
      {children}
    </motion.div>
  );
}

const PILARES = [
  {
    ic: "◐",
    t: "Presencia en tiempo real",
    d: "Ves quién trabaja dónde, línea por línea. Nunca dos personas a la vez en la misma línea: se previene antes, no se resuelve después.",
  },
  {
    ic: "⬡",
    t: "Ownership invisible",
    d: "El sistema sabe de quién es cada zona sin que nadie pida permiso. Tocás lo que necesites; si hay dueño, tu cambio se propone y se aprueba con un clic.",
  },
  {
    ic: "✦",
    t: "Impacto con resolución real",
    d: "Cambiás una firma y avisa, solo, a quién la usa de verdad — resolución cruzada, no coincidencia de texto. Sin falsos positivos.",
  },
  {
    ic: "⎇",
    t: "Todo sobre Git",
    d: "Un git clone basta. Commits, ramas, push y PRs siguen existiendo. laidea es una capa de coordinación, no un reemplazo.",
  },
];

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
    d: "Si tocás zona con dueño, tu cambio viaja como propuesta. El dueño lo aprueba con un clic. El impacto semántico avisa, solo, a quién depende de eso.",
  },
  {
    n: "03",
    t: "Se aplica al final",
    d: "Aprobado, se integra para todos en el acto. Commit y push siguen siendo Git de verdad: git clone basta para tener el proyecto completo.",
  },
];

const MARQUEE = [
  "Python", "TypeScript", "Go", "Rust",
  "presencia en vivo", "ownership invisible", "impacto real",
  "tentativo", "sobre Git", "sin CRDT", "sin ceremonia",
];

const NOTS = [
  "No es governance corporativo, permisos ni vigilancia.",
  "No reemplaza Git, GitHub ni tu IDE.",
  "No te bloquea antes de intentar: editar primero, siempre.",
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
  "Distribución de conocimiento: el líder deja de ser cuello de botella",
  "Todos los lenguajes, análisis siempre tibio, integraciones",
];

/* Mockup del producto en el hero: una "isla" que evoca el IDE real
   (sidebar de archivos + editor con presencia y aviso de impacto).
   Es decorativo — aria-hidden — pero vende la continuidad visual. */
function ProductPeek() {
  return (
    <div className="peek" aria-hidden>
      <div className="peek-bar">
        <span className="tl tl-r" /><span className="tl tl-y" /><span className="tl tl-g" />
        <span className="peek-title">workspace · laidea</span>
        <span className="peek-live"><i />3 en vivo</span>
      </div>
      <div className="peek-body">
        <aside className="peek-side">
          <span className="pf on">core/</span>
          <span className="pf"> sync.py</span>
          <span className="pf claim"> roster.py <em>Ana</em></span>
          <span className="pf"> impact.py</span>
          <span className="pf"> git.py</span>
        </aside>
        <div className="peek-code">
          <div className="ln"><span className="lnn">12</span><code><span className="kw">def</span> <span className="fn">claim</span>(path, user):</code></div>
          <div className="ln me"><span className="lnn">13</span><code>    owners[path] = user  <span className="cm"># vos</span></code></div>
          <div className="ln"><span className="lnn">14</span><code>    <span className="kw">return</span> Ownership(path)</code></div>
          <div className="ln other"><span className="lnn">15</span><code>    broadcast(owners)  <span className="cm"># Ana</span></code></div>
          <div className="ln"><span className="lnn">16</span><code></code></div>
          <div className="peek-toast">
            <b>Impacto</b> · cambiar <code>claim()</code> afecta a 4 usos reales →
            <span className="ok">se avisó solo</span>
          </div>
        </div>
      </div>
    </div>
  );
}

export function App() {
  const reduce = useReducedMotion();
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 24);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  // whileInView con reduce: mostramos el estado final sin animar.
  const reveal = reduce
    ? { initial: "show" as const }
    : { initial: "hidden" as const, whileInView: "show" as const };

  return (
    <>
      {/* Fondo: aurora que deriva lento + rejilla técnica enmascarada.
          El motion del aurora se apaga vía CSS (prefers-reduced-motion). */}
      <div className="aurora" aria-hidden>
        <i /><i /><i />
      </div>
      <div className="grid-bg" aria-hidden />

      <nav className={"nav" + (scrolled ? " scrolled" : "")}>
        <div className="wrap">
          <a className="brand" href="#top">la<b>idea</b></a>
          <div className="nav-links">
            <a href="#como">Cómo funciona</a>
            <a href="#pilares">Qué hace</a>
            <a href="#precio">Precio</a>
          </div>
          <div className="nav-cta">
            <a className="btn ghost sm" href={APP}>Entrar →</a>
          </div>
        </div>
      </nav>

      {/* HERO */}
      <header className="hero" id="top">
        <div className="wrap">
          <motion.div
            variants={stagger}
            initial="hidden"
            animate="show"
          >
            <motion.div variants={fadeUp}>
              <span className="pill">
                <span className="dot" /> En producción · probándose con devs reales
              </span>
            </motion.div>
            <motion.h1 variants={fadeUp}>
              Tu equipo toca el código.{" "}
              <span className="grad">El sistema se encarga de que nada se rompa.</span>
            </motion.h1>
            <motion.p className="sub" variants={fadeUp}>
              Coordinación en tiempo real sobre Git para equipos de 2 a 50.
              Presencia en vivo, ownership invisible y análisis de impacto
              con resolución real — sin la ceremonia de branches, PRs y reviews.
            </motion.p>
            <motion.div className="cta" variants={fadeUp}>
              <a className="btn primary" href={APP}>Probar ahora</a>
              <a className="btn ghost" href="#como">Ver cómo funciona</a>
            </motion.div>
            <motion.p className="hero-foot" variants={fadeUp}>
              No reemplaza Git, GitHub ni tu IDE: es una capa encima.
            </motion.p>
          </motion.div>

          <motion.div
            variants={fadeUp}
            initial="hidden"
            animate="show"
            transition={{ delay: 0.35 }}
          >
            <ProductPeek />
          </motion.div>

          <div className="marquee" aria-hidden>
            <ul>
              {[...MARQUEE, ...MARQUEE].map((m, i) => (
                <li key={i}>{m}</li>
              ))}
            </ul>
          </div>
        </div>
      </header>

      {/* TESIS */}
      <section className="thesis">
        <div className="wrap">
          <Reveal><div className="eyebrow">La tesis</div></Reveal>
          <Reveal delay={0.08}>
            <p className="big">
              Misma seguridad que tu flujo actual —branches, PRs, reviews—{" "}
              <span className="grad">sin la ceremonia</span>. El sistema sabe
              sin que nadie le pregunte.
            </p>
          </Reveal>
        </div>
      </section>

      {/* CÓMO FUNCIONA — 3 tiempos */}
      <section id="como">
        <div className="wrap">
          <Reveal><div className="eyebrow">Cómo funciona</div></Reveal>
          <Reveal delay={0.08}>
            <p className="big">Editás primero. Se negocia después. Se aplica al final.</p>
          </Reveal>
          <motion.div
            className="steps"
            variants={stagger}
            {...reveal}
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

      {/* PILARES */}
      <section id="pilares">
        <div className="wrap">
          <Reveal><div className="eyebrow">Qué hace, de verdad</div></Reveal>
          <Reveal delay={0.08}>
            <p className="big">
              Cuatro cosas, bien hechas.{" "}
              <span className="grad">Ninguna es humo.</span>
            </p>
          </Reveal>
          <motion.div
            className="cards"
            variants={stagger}
            {...reveal}
            viewport={{ once: true, amount: 0.2 }}
          >
            {PILARES.map((p) => (
              <motion.div
                key={p.t}
                className="glass"
                variants={fadeUp}
                whileHover={reduce ? undefined : { y: -6 }}
                transition={{ type: "spring", stiffness: 240, damping: 20 }}
              >
                <div className="glow" />
                <div className="ic">{p.ic}</div>
                <h3>{p.t}</h3>
                <p>{p.d}</p>
              </motion.div>
            ))}
          </motion.div>
          <Reveal delay={0.12} className="langs">
            <span>Análisis disponible para</span>
            <b>Python</b><b>TypeScript / JS</b><b>Go</b><b>Rust</b>
          </Reveal>
        </div>
      </section>

      {/* POR QUÉ ES DISTINTO */}
      <section>
        <div className="wrap">
          <Reveal><div className="eyebrow">Por qué es distinto</div></Reveal>
          <Reveal delay={0.08}>
            <p className="big">
              Git no previene colisiones. Live Share no entiende tu código.
              Tu IDE no coordina al equipo.{" "}
              <span className="grad">laidea es las tres cosas, a la vez, sobre Git.</span>
            </p>
          </Reveal>
        </div>
      </section>

      {/* LO QUE NO SOMOS */}
      <section>
        <div className="wrap">
          <Reveal><div className="eyebrow">Lo que NO somos</div></Reveal>
          <Reveal delay={0.08}>
            <p className="big">
              Vendemos coordinación, no control.{" "}
              <span className="grad">El dev nunca se siente vigilado.</span>
            </p>
          </Reveal>
          <motion.div
            className="nots"
            variants={stagger}
            {...reveal}
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

      {/* PRICING */}
      <section id="precio">
        <div className="wrap">
          <Reveal><div className="eyebrow">Precio</div></Reveal>
          <Reveal delay={0.08}>
            <p className="big">Gratis de verdad para empezar. Pagás cuando escalás.</p>
          </Reveal>
          <motion.div
            className="prices"
            variants={stagger}
            {...reveal}
            viewport={{ once: true, amount: 0.2 }}
          >
            <motion.div className="price" variants={fadeUp}>
              <div className="tier">Free · para siempre</div>
              <h4>Para tu equipo chico</h4>
              <p className="price-sub">Todo el core, sin asteriscos. Para equipos nuevos sin inercia.</p>
              <ul>
                {FREE.map((f) => <li key={f}>{f}</li>)}
              </ul>
              <a className="btn ghost full" href={APP}>Empezar gratis</a>
            </motion.div>
            <motion.div className="price pro" variants={fadeUp}>
              <span className="badge">Recomendado al crecer</span>
              <div className="tier">Premium · escala y profundidad</div>
              <h4>Cuando crecés</h4>
              <p className="price-sub">Más equipo, más repos, análisis más profundo y conocimiento distribuido.</p>
              <ul>
                {PRO.map((f) => <li key={f}>{f}</li>)}
              </ul>
              <a className="btn primary full" href={APP}>Entrar a laidea</a>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* CTA FINAL */}
      <section className="final">
        <div className="halo" aria-hidden />
        <div className="wrap">
          <Reveal>
            <h2>
              Misma vida, <span className="grad">menos dolor.</span>
            </h2>
          </Reveal>
          <Reveal delay={0.08}>
            <p className="final-sub">
              Editar primero. Negociar después. Aplicar al final.
              El sistema sabe sin que nadie le pregunte.
            </p>
          </Reveal>
          <Reveal delay={0.16} className="final-cta">
            <a className="btn primary lg" href={APP}>Entrar a laidea</a>
            <a className="btn ghost lg" href="#como">Cómo funciona</a>
          </Reveal>
        </div>
      </section>

      <footer>
        <div className="wrap">
          <div className="foot-l">
            <a className="brand" href="#top">la<b>idea</b></a>
            <p>multiplayer semantic coding · misma vida, menos dolor</p>
          </div>
          <div className="foot-r">
            <a href={APP}>Entrar</a>
            <a href="#como">Cómo funciona</a>
            <a href="#precio">Precio</a>
          </div>
        </div>
      </footer>
    </>
  );
}
