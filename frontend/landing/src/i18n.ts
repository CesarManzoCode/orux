export type Lang = "es" | "en";
const KEY = "orux_lang";

export function cargaLang(): Lang {
  try { return (localStorage.getItem(KEY) as Lang) || "es"; }
  catch { return "es"; }
}

export function guardaLang(l: Lang) {
  try { localStorage.setItem(KEY, l); } catch {}
}

export const T = {
  es: {
    // Nav
    nav_problema: "El problema",
    nav_pilares: "Qué hace",
    nav_como: "Cómo funciona",
    nav_precio: "Precio",
    nav_produccion: "en producción",
    nav_entrar: "Entrar",
    nav_arr: "→",

    // Hero
    hero_eyebrow: "En producción · equipos reales coordinando",
    hero_h1_1: "Tu equipo toca el código.",
    hero_h1_2: "El sistema coordina el riesgo.",
    hero_sub: "Una capa de coordinación en tiempo real sobre Git, para equipos de 2 a 50. Ownership, presencia e impacto resueltos antes de que el cambio llegue a producción — sin la ceremonia de branches, PRs y reviews.",
    hero_cta_primary: "Entrar a Orux",
    hero_cta_secondary: "Ver cómo funciona",
    hero_sig1: "presencia ·",
    hero_sig1_b: "por línea",
    hero_sig2: "ownership ·",
    hero_sig2_b: "invisible",
    hero_sig3: "impacto ·",
    hero_sig3_b: "resolución real",

    // Stage (mockup del IDE — aria-hidden, mayormente estático)
    stage_live: "4 en vivo",
    stage_mine: "vos",
    stage_clean: "sin colisiones",
    stage_impact_title: "Análisis de impacto",
    stage_impact_body1: "Cambiar",
    stage_impact_body2: "afecta",
    stage_impact_body3: "— resolución cruzada, no coincidencia de texto.",
    stage_impact_auto: "Se avisó solo a quien depende de esto",
    stage_prop_title: "Propuesta de Ana",
    stage_prop_meta: "sync.py ·",
    stage_prop_approve: "Aprobar",
    stage_prop_view: "Ver diff",
    stage_prop_pend: "pendiente · un clic la integra",

    // Trust
    trust: [
      { k: "Modelo", v_pre: "Sobre", v_b: "Git", v_post: " · git clone basta" },
      { k: "Conflictos", v_pre: "Se", v_b: "previene", v_post: ", no se fusiona · sin CRDT" },
      { k: "Granularidad", v_pre: "Presencia", v_b: "por línea", v_post: ", no por archivo" },
      { k: "Estado", v_pre: "", v_b: "en producción", v_post: " · equipos reales" },
    ],

    // Problema
    s01_k: "01 · El problema",
    s01_h_1: "El riesgo no está en el código.",
    s01_h_2: "Está en que nadie lo ve a tiempo.",
    s01_sub: "Dos personas tocan archivos relacionados. Nadie lo ve. El conflicto y el cambio que rompe a un tercero aparecen al final, en el merge — cuando ya cuesta caro.",
    risk_now: "Ahora · sin coordinación",
    risk_git: "Lo que Git ve",
    risk_you: "Vos ·",
    risk_collision: "colisión latente",
    risk_foot: "Git no previene colisiones: las",
    risk_foot_b: "descubre en el merge",
    risk_foot2: ". Live Share no entiende tu código. Tu IDE no coordina al equipo.",

    // Pilares
    s02_k: "02 · Qué hace, de verdad",
    s02_h_1: "Orux lo detecta solo,",
    s02_h_2: "sin que nadie le pregunte.",
    s02_sub: "Tres mecanismos reales, funcionando hoy. Ninguno es humo: corren en producción con devs reales.",
    mod1_title: "Presencia",
    mod1_h3: "Quién toca qué, en vivo",
    mod1_p: "Presencia por línea. Nunca dos en la misma: se previene antes, no se resuelve después.",
    mod2_title: "Ownership",
    mod2_h3: "De quién es cada zona",
    mod2_p: "El sistema lo sabe sin que nadie pida permiso. Hay dueño: tu cambio se propone, no se bloquea.",
    mod3_title: "Impacto",
    mod3_h3: "Qué se rompe si cambiás esto",
    mod3_p: "Cambiás una firma y avisa, solo, a quién la usa de verdad. Resolución cruzada, sin falsos positivos.",
    mod_own_me: "vos",
    mod_own_free: "libre",
    mod_impact_ok: "avisado automáticamente",

    // Flujo
    s03_k: "03 · Coordinación en tiempo real",
    s03_h_1: "La negociación ocurre dentro del editor,",
    s03_h_2: "no en una cola de PRs.",
    s03_sub: "Lo que antes era rama → PR → review → merge, ahora es proponer → aprobar → aplicar. Mismo control, sin la ceremonia.",
    flow: [
      {
        n: "01 · PROPONE",
        t: "El cambio viaja como propuesta",
        d: "Tocas una zona con dueño y sigues editando. Tu cambio no se descarta ni te frena: queda en cola, atado al archivo y a ti.",
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
    ],

    // Cómo funciona (pasos)
    s04_k: "04 · Cómo funciona",
    s04_h_1: "Editas primero. Se negocia después.",
    s04_h_2: "Se aplica al final.",
    s04_sub: "La tesis, en tres tiempos. Misma seguridad que tu flujo actual; el sistema sabe sin que nadie le pregunte.",
    pasos: [
      {
        n: "01",
        t: "Editas primero",
        d: "Abres el archivo y escribes. Sin pedir permiso, sin esperar una rama. La presencia en vivo te muestra dónde está cada quien antes de pisarse.",
      },
      {
        n: "02",
        t: "Se negocia después",
        d: "Si tocas zona con dueño, tu cambio viaja como propuesta. El dueño la aprueba con un clic. El impacto avisa, solo, a quién depende de eso.",
      },
      {
        n: "03",
        t: "Se aplica al final",
        d: "Aprobado, se integra para todos en el acto. Commit y push siguen siendo Git de verdad: git clone basta para tener el proyecto completo.",
      },
    ],

    // No somos
    s05_k: "05 · Lo que NO somos",
    s05_h_1: "Vendemos coordinación,",
    s05_h_2: "no control.",
    nots: [
      "No es governance corporativo, permisos ni vigilancia.",
      "No reemplaza Git, GitHub ni tu IDE: es una capa encima.",
      "No te bloquea antes de intentar — editar primero, siempre.",
      "No es un chatbot pegado a un editor.",
    ],

    // Pricing
    s06_k: "06 · Precio",
    s06_h_1: "Para equipos nuevos sin inercia,",
    s06_h_2: "empezar no cuesta.",
    s06_sub: "Gratis de verdad para empezar, sin asteriscos. Pagas cuando el equipo escala y necesita más profundidad.",
    free_tier: "Free · para siempre",
    free_h4: "Tu equipo chico",
    free_sub: "Todo el core de coordinación, sin recortes. Para equipos que empiezan.",
    free: [
      "Hasta 5 devs por equipo",
      "Coordinación completa: presencia, ownership, tentativo, Git",
      "Análisis de impacto con resolución real",
      "Un workspace por equipo · 2 lenguajes",
    ],
    free_cta: "Empezar gratis",
    pro_badge: "Recomendado al crecer",
    pro_tier: "Premium · escala y profundidad",
    pro_h4: "Cuando creces",
    pro_sub: "Más equipo, más repos, análisis más profundo y conocimiento distribuido.",
    pro: [
      "Equipos grandes, multi-proyecto y organización",
      "Impacto transitivo y entre repos",
      "Conocimiento distribuido: el líder deja de ser cuello de botella",
      "Todos los lenguajes, análisis siempre tibio, integraciones",
    ],
    pro_cta: "Entrar a Orux",

    // Final
    final_h2: "Misma vida, menos dolor.",
    final_sub: "Editar primero. Negociar después. Aplicar al final. El sistema sabe sin que nadie le pregunte.",
    final_cta: "Entrar a Orux",
    final_ghost: "Cómo funciona",

    // Footer
    foot_tagline: "multiplayer semantic coding · misma vida, menos dolor",
    foot_enter: "Entrar",
    foot_what: "Qué hace",
    foot_how: "Cómo funciona",
    foot_price: "Precio",

    // Lang
    lang_es: "Español",
    lang_en: "English",
  },

  en: {
    // Nav
    nav_problema: "The problem",
    nav_pilares: "What it does",
    nav_como: "How it works",
    nav_precio: "Pricing",
    nav_produccion: "in production",
    nav_entrar: "Sign in",
    nav_arr: "→",

    // Hero
    hero_eyebrow: "In production · real teams coordinating",
    hero_h1_1: "Your team touches the code.",
    hero_h1_2: "The system coordinates the risk.",
    hero_sub: "A real-time coordination layer on top of Git, for teams of 2 to 50. Ownership, presence and impact resolved before changes reach production — without the ceremony of branches, PRs and reviews.",
    hero_cta_primary: "Enter Orux",
    hero_cta_secondary: "See how it works",
    hero_sig1: "presence ·",
    hero_sig1_b: "by line",
    hero_sig2: "ownership ·",
    hero_sig2_b: "invisible",
    hero_sig3: "impact ·",
    hero_sig3_b: "real resolution",

    // Stage
    stage_live: "4 live",
    stage_mine: "you",
    stage_clean: "no collisions",
    stage_impact_title: "Impact analysis",
    stage_impact_body1: "Changing",
    stage_impact_body2: "affects",
    stage_impact_body3: "— cross-module resolution, not text matching.",
    stage_impact_auto: "Notified automatically to whoever depends on this",
    stage_prop_title: "Ana's proposal",
    stage_prop_meta: "sync.py ·",
    stage_prop_approve: "Approve",
    stage_prop_view: "View diff",
    stage_prop_pend: "pending · one click integrates it",

    // Trust
    trust: [
      { k: "Model", v_pre: "On", v_b: "Git", v_post: " · git clone is enough" },
      { k: "Conflicts", v_pre: "It", v_b: "prevents", v_post: ", not merges · no CRDT" },
      { k: "Granularity", v_pre: "Presence", v_b: "by line", v_post: ", not by file" },
      { k: "Status", v_pre: "", v_b: "in production", v_post: " · real teams" },
    ],

    // Problema
    s01_k: "01 · The problem",
    s01_h_1: "The risk isn't in the code.",
    s01_h_2: "It's that nobody sees it in time.",
    s01_sub: "Two people touch related files. Nobody sees it. The conflict and the change that breaks a third party show up at the end, in the merge — when it's already expensive.",
    risk_now: "Now · no coordination",
    risk_git: "What Git sees",
    risk_you: "You ·",
    risk_collision: "latent collision",
    risk_foot: "Git doesn't prevent collisions: it",
    risk_foot_b: "discovers them at merge",
    risk_foot2: ". Live Share doesn't understand your code. Your IDE doesn't coordinate the team.",

    // Pilares
    s02_k: "02 · What it really does",
    s02_h_1: "Orux detects it alone,",
    s02_h_2: "without anyone asking.",
    s02_sub: "Three real mechanisms, working today. None of it is smoke: running in production with real devs.",
    mod1_title: "Presence",
    mod1_h3: "Who's touching what, live",
    mod1_p: "Presence by line. Never two on the same: prevented before, not resolved after.",
    mod2_title: "Ownership",
    mod2_h3: "Who owns each zone",
    mod2_p: "The system knows without anyone asking for permission. There's an owner: your change is proposed, not blocked.",
    mod3_title: "Impact",
    mod3_h3: "What breaks if you change this",
    mod3_p: "You change a signature and it notifies, alone, whoever uses it for real. Cross-module resolution, no false positives.",
    mod_own_me: "you",
    mod_own_free: "free",
    mod_impact_ok: "automatically notified",

    // Flujo
    s03_k: "03 · Real-time coordination",
    s03_h_1: "Negotiation happens inside the editor,",
    s03_h_2: "not in a PR queue.",
    s03_sub: "What was once branch → PR → review → merge, is now propose → approve → apply. Same control, without the ceremony.",
    flow: [
      {
        n: "01 · PROPOSES",
        t: "The change travels as a proposal",
        d: "You touch a zone with an owner and keep editing. Your change isn't discarded or blocked: it's queued, tied to the file and to you.",
        chip: { txt: "diff ready · no branch", cls: "" },
      },
      {
        n: "02 · RESOLVES",
        t: "The owner decides with one click",
        d: "They get the proposal with impact already calculated. Approves or asks for adjustment. No meeting, no PR, no waiting for the lead.",
        chip: { txt: "pending · 1 click", cls: "wt" },
      },
      {
        n: "03 · APPLIES",
        t: "Integrated for the whole team",
        d: "Approved, the change appears in everyone's editor instantly and stays as a real Git commit. Nobody was left out of sync.",
        chip: { txt: "applied · in Git", cls: "go" },
      },
    ],

    // Cómo funciona
    s04_k: "04 · How it works",
    s04_h_1: "Edit first. Negotiate after.",
    s04_h_2: "Apply at the end.",
    s04_sub: "The thesis, in three steps. Same safety as your current flow; the system knows without anyone asking.",
    pasos: [
      {
        n: "01",
        t: "Edit first",
        d: "Open the file and write. No asking for permission, no waiting for a branch. Live presence shows you where everyone is before stepping on each other.",
      },
      {
        n: "02",
        t: "Negotiate after",
        d: "If you touch a zone with an owner, your change travels as a proposal. The owner approves with one click. Impact notifies, alone, whoever depends on it.",
      },
      {
        n: "03",
        t: "Apply at the end",
        d: "Approved, it integrates for everyone instantly. Commit and push are still real Git: git clone is enough to have the full project.",
      },
    ],

    // No somos
    s05_k: "05 · What we are NOT",
    s05_h_1: "We sell coordination,",
    s05_h_2: "not control.",
    nots: [
      "Not corporate governance, permissions or surveillance.",
      "Doesn't replace Git, GitHub or your IDE: it's a layer on top.",
      "Doesn't block you before trying — edit first, always.",
      "Not a chatbot glued to an editor.",
    ],

    // Pricing
    s06_k: "06 · Pricing",
    s06_h_1: "For new teams without inertia,",
    s06_h_2: "starting is free.",
    s06_sub: "Truly free to start, no asterisks. You pay when the team scales and needs more depth.",
    free_tier: "Free · forever",
    free_h4: "Your small team",
    free_sub: "Full coordination core, no cutbacks. For teams that are starting.",
    free: [
      "Up to 5 devs per team",
      "Full coordination: presence, ownership, tentative, Git",
      "Impact analysis with real resolution",
      "One workspace per team · 2 languages",
    ],
    free_cta: "Start for free",
    pro_badge: "Recommended as you grow",
    pro_tier: "Premium · scale and depth",
    pro_h4: "When you grow",
    pro_sub: "More team, more repos, deeper analysis and distributed knowledge.",
    pro: [
      "Large teams, multi-project and organization",
      "Transitive and cross-repo impact",
      "Distributed knowledge: the lead stops being a bottleneck",
      "All languages, always-warm analysis, integrations",
    ],
    pro_cta: "Enter Orux",

    // Final
    final_h2: "Same life, less pain.",
    final_sub: "Edit first. Negotiate after. Apply at the end. The system knows without anyone asking.",
    final_cta: "Enter Orux",
    final_ghost: "How it works",

    // Footer
    foot_tagline: "multiplayer semantic coding · same life, less pain",
    foot_enter: "Sign in",
    foot_what: "What it does",
    foot_how: "How it works",
    foot_price: "Pricing",

    // Lang
    lang_es: "Español",
    lang_en: "English",
  },
} as const;

export type Traducciones = typeof T["es"];
