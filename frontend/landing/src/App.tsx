import { useEffect, useState, type ReactNode } from "react";
import { motion, type Variants } from "framer-motion";

const APP = "/app"; // el IDE vive acá (capa 23b)

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 28 },
  show: { opacity: 1, y: 0, transition: { duration: 0.7, ease: [0.16, 1, 0.3, 1] } },
};
const stagger: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.12 } },
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
    d: "Cambiás una firma y avisa, solo, a quién la usa de verdad — resolución cruzada, no coincidencia de texto. Sin falsos positivos. Python, TS/JS, Go y Rust.",
  },
  {
    ic: "⎇",
    t: "Todo sobre Git",
    d: "Un git clone basta. Commits, ramas, push y PRs siguen existiendo. laidea es una capa de coordinación, no un reemplazo.",
  },
];

const MARQUEE = [
  "Python", "TypeScript", "Go", "Rust", "presencia en vivo",
  "ownership invisible", "impacto real", "tentativo", "sobre Git",
];

const NOTS = [
  "No es governance corporativo, permisos ni vigilancia.",
  "No reemplaza Git, GitHub ni tu IDE.",
  "No te bloquea antes de intentar: editar primero, siempre.",
  "No es un chatbot pegado a un editor.",
];

export function App() {
  const [scrolled, setScrolled] = useState(false);
  useEffect(() => {
    const on = () => setScrolled(window.scrollY > 24);
    on();
    window.addEventListener("scroll", on, { passive: true });
    return () => window.removeEventListener("scroll", on);
  }, []);

  return (
    <>
      <div className="aurora" aria-hidden>
        <i /><i /><i />
      </div>
      <div className="grid-bg" aria-hidden />

      <nav className={"nav" + (scrolled ? " scrolled" : "")}>
        <div className="wrap">
          <div className="brand">la<b>idea</b></div>
          <a className="btn ghost" href={APP}>Entrar →</a>
        </div>
      </nav>

      {/* HERO */}
      <header className="hero">
        <div className="wrap">
          <motion.div
            variants={stagger}
            initial="hidden"
            animate="show"
          >
            <motion.div variants={fadeUp}>
              <span className="pill"><span className="dot" /> En producción · probándose con devs reales</span>
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
              <a className="btn ghost" href="#como">Cómo funciona</a>
            </motion.div>
            <motion.p className="hero-foot" variants={fadeUp}>
              No reemplaza Git, GitHub ni tu IDE: es una capa encima.
            </motion.p>
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

      {/* CÓMO FUNCIONA */}
      <section id="como">
        <div className="wrap">
          <Reveal><div className="eyebrow">Cómo funciona</div></Reveal>
          <Reveal delay={0.08}>
            <p className="big">Editás primero. Se negocia después. Se aplica al final.</p>
          </Reveal>
          <motion.div
            className="cards"
            variants={stagger}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.2 }}
          >
            {PILARES.map((p) => (
              <motion.div
                key={p.t}
                className="glass"
                variants={fadeUp}
                whileHover={{ y: -6 }}
                transition={{ type: "spring", stiffness: 240, damping: 20 }}
              >
                <div className="glow" />
                <div className="ic">{p.ic}</div>
                <h3>{p.t}</h3>
                <p>{p.d}</p>
              </motion.div>
            ))}
          </motion.div>
        </div>
      </section>

      {/* CATEGORÍA NUEVA */}
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
          <motion.div
            className="nots"
            variants={stagger}
            initial="hidden"
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

      {/* PRICING */}
      <section>
        <div className="wrap">
          <Reveal><div className="eyebrow">Precio</div></Reveal>
          <Reveal delay={0.08}>
            <p className="big">Gratis de verdad para empezar. Pagás cuando escalás.</p>
          </Reveal>
          <motion.div
            className="prices"
            variants={stagger}
            initial="hidden"
            whileInView="show"
            viewport={{ once: true, amount: 0.2 }}
          >
            <motion.div className="price" variants={fadeUp}>
              <div className="tier">Free · para siempre</div>
              <h4>Para tu equipo chico</h4>
              <ul>
                <li>Hasta 5 devs por equipo</li>
                <li>Coordinación completa: presencia, ownership, tentativo, Git</li>
                <li>Análisis de impacto con resolución real</li>
                <li>Un workspace por equipo</li>
              </ul>
            </motion.div>
            <motion.div className="price pro" variants={fadeUp}>
              <div className="tier">Premium · escala y profundidad</div>
              <h4>Cuando crecés</h4>
              <ul>
                <li>Equipos grandes, multi-proyecto, organización</li>
                <li>Impacto transitivo y entre repos</li>
                <li>Distribución de conocimiento: el líder deja de ser cuello de botella</li>
                <li>Todos los lenguajes, análisis siempre tibio, integraciones</li>
              </ul>
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
          <Reveal delay={0.1}>
            <a className="btn primary" href={APP}>Entrar a laidea</a>
          </Reveal>
        </div>
      </section>

      <footer>
        <div className="wrap">
          <div className="brand">la<b>idea</b></div>
          <div>multiplayer semantic coding · misma vida, menos dolor</div>
        </div>
      </footer>
    </>
  );
}
