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
    nav_problema: "Problema",
    nav_pilares: "Qué hace",
    nav_como: "Cómo funciona",
    nav_seguridad: "Seguridad",
    nav_faq: "FAQ",
    nav_precio: "Precio",
    nav_produccion: "en producción",
    nav_entrar: "Entrar",
    nav_arr: "→",

    // Hero
    hero_eyebrow: "En producción · equipos reales coordinando en vivo",
    hero_audience: "Para equipos de 2 a 50 devs · self-host con Docker · gratis hasta 5",
    hero_h1_1: "Quién toca qué. De quién es. Qué rompe.",
    hero_h1_2: "En tiempo real, sobre el Git que ya usas.",
    hero_sub: "Orux es la capa de coordinación en tiempo real sobre Git para equipos de 2 a 50 devs. Presencia por línea, ownership vivo y análisis de impacto resueltos antes del merge — sin reemplazar GitHub, GitLab ni tu IDE.",
    hero_cta_primary: "Crear tu workspace",
    hero_cta_secondary: "Cómo funciona",
    hero_time: "60 segundos para empezar · sin tarjeta",
    hero_micro: "Sin trial · sin instalación · git clone sigue funcionando.",
    hero_sig1: "Presencia ·",
    hero_sig1_b: "te avisa antes de pisar a alguien",
    hero_sig2: "Ownership ·",
    hero_sig2_b: "sabe de quién es sin preguntar",
    hero_sig3: "Impacto ·",
    hero_sig3_b: "muestra qué rompes al cambiar una firma",

    // Stage caption (microcopy bajo el IDE mock)
    stage_cap_aria: "Resumen de lo que se ve en el editor de ejemplo",
    stage_cap_1: "4 devs en vivo.",
    stage_cap_2: "Ana edita sync.py · tú editas roster.py.",
    stage_cap_3: "claim() cambió de firma:",
    stage_cap_4: "Orux detectó 4 usos · propuesta de Ana lista para aprobar.",

    // Stage interno (IDE mock — aria-hidden)
    stage_live: "4 en vivo",
    stage_mine: "tú",
    stage_clean: "sin colisiones",
    stage_impact_title: "Análisis de impacto",
    stage_impact_body1: "Cambiar",
    stage_impact_body2: "afecta",
    stage_impact_count: "usos",
    stage_impact_body3: "— resolución cruzada, no coincidencia de texto.",
    stage_impact_auto: "Se avisó solo a quien depende de esto",
    stage_prop_title: "Propuesta de Ana",
    stage_prop_meta: "sync.py ·",
    stage_prop_approve: "Aprobar",
    stage_prop_view: "Ver diff",
    stage_prop_pend: "pendiente · un clic la integra",
    stage_synced: "sincronizado",
    stage_phase_edit: "Ana edita",
    stage_phase_detect: "Impacto detectado",
    stage_phase_propose: "Propuesta lista",
    stage_phase_synced: "Sincronizado",

    // Trust — señales verificables (no claims sociales)
    trust: [
      { k: "Arquitectura", v_pre: "Capa", v_b: "sobre Git", v_post: " · git clone basta" },
      { k: "Conflictos", v_pre: "Se", v_b: "previenen", v_post: ", no se fusionan · sin CRDT" },
      { k: "Granularidad", v_pre: "Presencia", v_b: "por línea", v_post: ", no por archivo" },
      { k: "Despliegue", v_pre: "", v_b: "Self-hostable", v_post: " · Docker · tu token nunca se guarda" },
    ],

    // Problema (con comparativa antes/después)
    s01_k: "01 · El problema",
    s01_h_1: "El conflicto no se evita revisando más.",
    s01_h_2: "Se evita viéndolo en el momento.",
    s01_sub: "PRs, reviews y merges son la reacción tardía a algo que ya pasó. Orux lo intercepta cuando todavía cuesta nada.",
    cmp_head_left: "Hoy · branches + PRs",
    cmp_head_right: "Con Orux",
    cmp_rows: [
      { topic: "Conflictos", left: "Aparecen al merge, cuando ya cuesta caro deshacer.", right: "Se previenen en vivo: nadie pisa la misma línea." },
      { topic: "Ownership",  left: "Convención oral o CODEOWNERS desactualizado.",       right: "El sistema sabe quién toca qué, sin pedir permiso." },
      { topic: "Impacto",    left: "Lo descubre el CI roto o el reviewer atento.",        right: "Cambias una firma y avisa solo a quien la usa." },
      { topic: "Negociación", left: "Rama → PR → review → ida y vuelta → merge.",         right: "Propuesta dentro del editor, un clic la aplica." },
      { topic: "Conocimiento", left: "Vive en la cabeza del líder. Cuello de botella.",    right: "Se distribuye solo: cada quien ve qué depende de qué." },
    ],
    cmp_foot: "Git no previene colisiones: ",
    cmp_foot_b: "las descubre en el merge. Orux las intercepta antes.",

    // Pilares — WHAT/WHY/BENEFIT
    s02_k: "02 · Qué hace, de verdad",
    s02_h_1: "Tres mecanismos reales,",
    s02_h_2: "funcionando hoy en producción.",
    s02_sub: "Ninguno es humo: corren en producción con devs reales. Cada uno responde a un dolor concreto del flujo actual.",
    mod_labels: { what: "QUÉ", why: "QUE EVITA", benefit: "PARA EL EQUIPO" },
    mod1_title: "Presencia",
    mod1_h3: "Quién toca qué, en vivo",
    mod1_what: "Presencia por línea, no por archivo. El cursor de cada quien queda visible.",
    mod1_why: "Que dos personas editen la misma zona sin saberlo y choquen en el merge.",
    mod1_benefit: "Editas con la certeza de que nadie está pisando lo mismo en otra pestaña.",
    mod2_title: "Ownership",
    mod2_h3: "De quién es cada zona",
    mod2_what: "Cada archivo tiene dueño implícito, derivado del uso real. Persistido y reasignable.",
    mod2_why: "La pregunta '¿puedo tocar esto?' en Slack o el CODEOWNERS que nadie actualiza.",
    mod2_benefit: "Tu cambio sobre código ajeno viaja como propuesta — no te frena ni invade al dueño.",
    mod3_title: "Impacto",
    mod3_h3: "Qué se rompe si cambias esto",
    mod3_what: "Análisis semántico real: AST y resolución de referencias, no coincidencia de texto.",
    mod3_why: "Romper a un tercero y enterarse en el CI, en review o en producción.",
    mod3_benefit: "Solo los afectados reciben el aviso, en el momento. Sin spamear al equipo.",
    mod_own_me: "tú",
    mod_own_free: "libre",
    mod_impact_ok: "avisado automáticamente",

    // Flujo (absorbe los 'pasos')
    s03_k: "03 · Cómo funciona, en vivo",
    s03_h_1: "Tres pasos. Dentro del editor.",
    s03_h_2: "Sin salir a una cola de PRs.",
    s03_sub: "Lo que antes era rama → PR → review → merge ahora es proponer → aprobar → aplicar. Misma seguridad, sin ceremonia.",
    flow: [
      {
        n: "01 · EDITAS",
        t: "Abre el archivo y escribe",
        d: "Sin pedir permiso, sin esperar una rama. La presencia en vivo te muestra dónde está cada quien — si te acercas a una zona ocupada, lo ves antes de tocarla.",
        chip: { txt: "sin rama · sin PR", cls: "" },
      },
      {
        n: "02 · ORUX DETECTA",
        t: "El sistema cruza ownership e impacto",
        d: "Si la zona tiene dueño, tu cambio se convierte en propuesta. Si cambiaste una firma, Orux calcula quién la usa de verdad — solo a esos les llega el aviso.",
        chip: { txt: "propuesta · impacto calculado", cls: "wt" },
      },
      {
        n: "03 · SE APLICA",
        t: "Un clic del dueño y queda en Git",
        d: "El dueño aprueba con un clic. El cambio aparece en el editor de todos al instante y queda como commit Git real. git clone sigue bastando para tener el proyecto.",
        chip: { txt: "commit Git real · al instante", cls: "go" },
      },
    ],

    // No somos
    s04_k: "04 · Lo que NO somos",
    s04_h_1: "Vendemos coordinación,",
    s04_h_2: "no control.",
    nots: [
      "No es governance corporativo, permisos ni vigilancia del código.",
      "No reemplaza Git, GitHub ni tu IDE: es una capa encima.",
      "No te bloquea antes de intentar — editas primero, siempre.",
      "No es un chatbot pegado a un editor.",
    ],

    // FAQ
    s05_k: "05 · Preguntas frecuentes",
    s05_h_1: "Lo que el equipo pregunta",
    s05_h_2: "antes de probarlo.",
    s05_sub: "Respuestas directas, sin humo. Si falta una, escríbenos.",
    faq: [
      {
        q: "¿Orux reemplaza Git o GitHub?",
        a: "No. Orux es una capa encima de Git. Cada workspace es un repo Git real: commit, push y git clone funcionan como siempre. GitHub o GitLab siguen siendo el origen — tus PRs, issues y Actions viven ahí, no acá. Si dejás Orux mañana, el repo queda intacto.",
      },
      {
        q: "¿Tengo que cambiar de IDE?",
        a: "Para empezar, sí: la versión actual es una web app (editor en el navegador). Plugins para VSCode y JetBrains están en el roadmap — la idea es llevar la coordinación a tu IDE, no obligarte a abandonarlo.",
      },
      {
        q: "¿Cómo funciona el ownership? ¿Me bloquea?",
        a: "Nunca te bloquea. Si tocas una zona con dueño, tu cambio viaja como propuesta con el impacto ya calculado. El dueño aprueba con un clic. Edita primero, negocia después. El primero que toca un archivo se vuelve su dueño; un admin del workspace puede reasignar cuando hace falta.",
      },
      {
        q: "¿Qué pasa si dos personas editan la misma línea?",
        a: "No pasa. La presencia por línea se reserva en cuanto la primera persona la toca: la segunda lo ve antes de escribir. No usamos CRDT — la tesis es prevenir, no fusionar.",
      },
      {
        q: "¿Qué lenguajes entiende el análisis de impacto?",
        a: "Hoy: Python y JavaScript/TypeScript. El análisis es real (AST y resolución de referencias), no coincidencia de texto. Más lenguajes a medida que escala el uso real — sin promesas que no podamos cumplir.",
      },
      {
        q: "¿Qué pasa con la privacidad del código?",
        a: "Orux es self-hostable: corré tu propia instancia con Docker, tu código nunca sale de tu infraestructura. La versión hospedada en orux.space clona tu repo bajo demanda y el token de Git va efímero — pasa por env del subprocess, nunca se guarda en disco, en logs ni en la URL.",
      },
      {
        q: "¿Sirve para equipos pequeños o grandes?",
        a: "Diseñado para 2 a 50 devs por equipo. Free cubre hasta 5. Arriba de eso, Premium agrega multi-repo y análisis transitivo. Equipos de más de 50 funcionan, pero el sweet spot es 2 a 50.",
      },
      {
        q: "¿Puedo usarlo offline?",
        a: "No. La tesis depende del estado compartido en tiempo real. Si te quedas sin red el editor te lo avisa y para los cambios destructivos hasta reconectar.",
      },
      {
        q: "¿Hay plan gratuito de verdad?",
        a: "Sí: hasta 5 devs, un workspace, core completo (presencia + ownership + impacto + Git). Sin trial, sin tarjeta, sin asteriscos. Pagás solo si el equipo crece o necesita análisis multi-repo.",
      },
    ],

    // Audiencia (para quién es)
    s_aud_k: "Para quién es",
    s_aud_h_1: "Diseñado para tres situaciones",
    s_aud_h_2: "donde la coordinación duele de verdad.",
    s_aud_sub: "No es una herramienta universal. Funciona mejor cuando la coordinación es asíncrona, el código todavía cabe en una cabeza y todavía no es tarde para instaurar el flujo.",
    aud: [
      {
        t: "Founder técnico · 2 a 5 devs",
        d: "Estás escribiendo el código y armando el equipo a la vez. Cada bloqueo cuesta una tarde tuya. Orux te quita el coste de coordinar sin meter governance corporativo.",
        b: ["Workspace en minutos, sin governance", "Gratis para siempre hasta 5 devs", "Self-host opcional si el cliente lo exige"],
      },
      {
        t: "Open source que arranca",
        d: "Contribuidores asíncronos, sin standups, sin Slack común. CODEOWNERS envejece mal y los conflictos los descubre el CI.",
        b: ["Ownership vivo, no archivo desactualizado", "Self-host con Docker, repo Git real", "Visible para nuevos sin reunión de onboarding"],
      },
      {
        t: "Equipo medio · 5 a 50 devs",
        d: "El líder ya no recuerda quién toca qué. El conocimiento vive en su cabeza y se vuelve cuello de botella. Orux distribuye el impacto sin reuniones nuevas.",
        b: ["Conocimiento distribuido por uso real", "Impacto entre repos en Premium", "Convive con tu GitHub/GitLab existente"],
      },
    ],

    // Seguridad / privacidad
    s_sec_k: "Seguridad y privacidad",
    s_sec_h_1: "Tu código no se vuelve nuestro problema.",
    s_sec_h_2: "Auditable, self-host y reversible.",
    s_sec_sub: "Orux se monta encima de Git: si te vas mañana, el repositorio queda intacto. La capa de coordinación es propiedad tuya, no rehén.",
    sec: [
      {
        t: "Self-host con Docker",
        d: "Una imagen, un docker compose up. Tu código nunca sale de tu infraestructura. Mismo binario que la versión hospedada.",
      },
      {
        t: "Token Git efímero, jamás guardado",
        d: "Cuando haces push, tu token pasa solo por el env del subprocess. Nunca en disco, ni en logs, ni en la URL, ni en .git/config. Salida scrubeada.",
      },
      {
        t: "Capa sobre Git, no rehén",
        d: "Cada workspace es un repo Git real. git clone basta. Si dejás Orux, te llevás el historial completo en un comando.",
      },
      {
        t: "Sin telemetría del contenido",
        d: "No leemos tu código para entrenar nada. El análisis de impacto corre local al server (tuyo si self-host). No hay LLM en el camino crítico.",
      },
      {
        t: "Open core, auditable",
        d: "El núcleo está en abierto. Podés leer cómo manejamos los tokens, el ownership y la propagación de cambios. Sin caja negra.",
      },
      {
        t: "Reversible en un comando",
        d: "Desinstalar Orux es git clone. No hay datos atrapados, no hay export raro, no hay vendor lock-in. Como debería ser una capa.",
      },
    ],

    // Pricing
    s06_k: "06 · Precio",
    s06_h_1: "Empezar es gratis.",
    s06_h_2: "Pagas cuando el equipo crece.",
    s06_sub: "Sin trial, sin tarjeta. El core completo de coordinación está en Free para siempre. Lo que se paga es escala y profundidad, no la funcionalidad básica.",
    free_tier: "Free · para siempre",
    free_h4: "Para el equipo que arranca",
    free_sub: "El core completo de coordinación, no una versión recortada. Lo que se limita es escala — no la tesis.",
    free: [
      "Hasta 5 devs en vivo en un workspace",
      "Análisis profundo de impacto en Python y TypeScript",
      "Ownership e impacto directo · sin merge sorpresa",
      "Self-hosted con Docker · tu código en tu infra",
    ],
    free_cta: "Probar gratis",
    pro_badge: "Recomendado al crecer",
    pro_tier: "Premium · cuando escala",
    pro_h4: "Cuando el equipo crece",
    pro_sub: "Sin topes de equipo, lenguajes que se suman, impacto que cruza repos y análisis siempre tibio. Para cuando el líder ya no puede ser el cuello de botella.",
    pro: [
      "Equipo sin tope · workspaces ilimitados por equipo",
      "Go, Rust, Java y Kotlin con la misma profundidad",
      "Impacto transitivo y entre repos · conocimiento distribuido",
      "Análisis siempre tibio · sin pico al volver al trabajo",
    ],
    pro_cta: "Empezar gratis · upgrade cuando importe",

    // Final CTA
    final_h2: "Tu equipo ya coordina. Mal.",
    final_sub: "Standups para saber qué tocaste. PRs para descubrir lo que rompiste. Reuniones para mover una firma. Hay un camino más corto — sin perder seguridad.",
    final_cta: "Crear tu workspace",
    final_ghost: "Cómo funciona",
    final_micro: "Gratis hasta 5 devs · sin trial · sin tarjeta · te lleva 60 segundos.",

    // Sticky mobile CTA
    sticky_label: "Listo cuando quieras",
    sticky_cta: "Crear workspace",

    // Footer
    foot_tagline: "Coordinación en tiempo real sobre Git · para equipos de 2 a 50",
    foot_enter: "Entrar",
    foot_what: "Qué hace",
    foot_how: "Cómo funciona",
    foot_faq: "FAQ",
    foot_price: "Precio",
    foot_copy: "© 2026 Orux",

    // Lang
    lang_es: "Español",
    lang_en: "English",
  },

  en: {
    // Nav
    nav_problema: "Problem",
    nav_pilares: "What it does",
    nav_como: "How it works",
    nav_seguridad: "Security",
    nav_faq: "FAQ",
    nav_precio: "Pricing",
    nav_produccion: "in production",
    nav_entrar: "Sign in",
    nav_arr: "→",

    // Hero
    hero_eyebrow: "In production · real teams coordinating live",
    hero_audience: "For teams of 2 to 50 devs · self-host with Docker · free up to 5",
    hero_h1_1: "Who touches what. Who owns it. What breaks.",
    hero_h1_2: "In real time, on the Git you already use.",
    hero_sub: "Orux is the real-time coordination layer on top of Git for teams of 2 to 50 devs. Per-line presence, live ownership and impact analysis resolved before the merge — without replacing GitHub, GitLab or your IDE.",
    hero_cta_primary: "Create your workspace",
    hero_cta_secondary: "How it works",
    hero_time: "60 seconds to start · no card",
    hero_micro: "No trial · no install · git clone still works.",
    hero_sig1: "Presence ·",
    hero_sig1_b: "warns you before stepping on someone",
    hero_sig2: "Ownership ·",
    hero_sig2_b: "knows whose it is without asking",
    hero_sig3: "Impact ·",
    hero_sig3_b: "shows what breaks when you change a signature",

    // Stage caption
    stage_cap_aria: "Summary of what is shown in the example editor",
    stage_cap_1: "4 devs live.",
    stage_cap_2: "Ana edits sync.py · you edit roster.py.",
    stage_cap_3: "claim() signature changed:",
    stage_cap_4: "Orux detected 4 usages · Ana's proposal ready to approve.",

    // Stage interno
    stage_live: "4 live",
    stage_mine: "you",
    stage_clean: "no collisions",
    stage_impact_title: "Impact analysis",
    stage_impact_body1: "Changing",
    stage_impact_body2: "affects",
    stage_impact_count: "callers",
    stage_impact_body3: "— cross-module resolution, not text matching.",
    stage_impact_auto: "Notified automatically to whoever depends on this",
    stage_prop_title: "Ana's proposal",
    stage_prop_meta: "sync.py ·",
    stage_prop_approve: "Approve",
    stage_prop_view: "View diff",
    stage_prop_pend: "pending · one click integrates it",
    stage_synced: "synced",
    stage_phase_edit: "Ana editing",
    stage_phase_detect: "Impact detected",
    stage_phase_propose: "Proposal ready",
    stage_phase_synced: "Synced",

    // Trust
    trust: [
      { k: "Architecture", v_pre: "Layer", v_b: "on top of Git", v_post: " · git clone is enough" },
      { k: "Conflicts", v_pre: "", v_b: "Prevented", v_post: ", not merged · no CRDT" },
      { k: "Granularity", v_pre: "Presence", v_b: "by line", v_post: ", not by file" },
      { k: "Deployment", v_pre: "", v_b: "Self-hostable", v_post: " · Docker · your token is never stored" },
    ],

    // Problem
    s01_k: "01 · The problem",
    s01_h_1: "Conflicts aren't avoided by reviewing more.",
    s01_h_2: "They're avoided by seeing them as they happen.",
    s01_sub: "PRs, reviews and merges are the late reaction to something that already happened. Orux intercepts it while it still costs nothing.",
    cmp_head_left: "Today · branches + PRs",
    cmp_head_right: "With Orux",
    cmp_rows: [
      { topic: "Conflicts",  left: "Surface at merge, when undoing is already expensive.", right: "Prevented live: nobody touches the same line." },
      { topic: "Ownership",  left: "Oral convention or stale CODEOWNERS.",                  right: "The system knows who touches what, no permission needed." },
      { topic: "Impact",      left: "Discovered by broken CI or an attentive reviewer.",     right: "Change a signature, only its callers get notified." },
      { topic: "Negotiation", left: "Branch → PR → review → back and forth → merge.",       right: "Proposal inside the editor, one click applies it." },
      { topic: "Knowledge",   left: "Lives in the lead's head. Bottleneck.",                 right: "Distributed by itself: everyone sees what depends on what." },
    ],
    cmp_foot: "Git doesn't prevent collisions: ",
    cmp_foot_b: "it discovers them at merge. Orux intercepts them before.",

    // Pillars
    s02_k: "02 · What it really does",
    s02_h_1: "Three real mechanisms,",
    s02_h_2: "running in production today.",
    s02_sub: "Not smoke: running in production with real devs. Each one answers a concrete pain in today's flow.",
    mod_labels: { what: "WHAT", why: "AVOIDS", benefit: "FOR THE TEAM" },
    mod1_title: "Presence",
    mod1_h3: "Who's touching what, live",
    mod1_what: "Per-line presence, not per-file. Each person's cursor is visible.",
    mod1_why: "Two people editing the same zone without knowing, clashing at merge.",
    mod1_benefit: "You edit knowing nobody is stepping on the same code in another tab.",
    mod2_title: "Ownership",
    mod2_h3: "Who owns each zone",
    mod2_what: "Each file has an implicit owner, derived from real use. Persisted and reassignable.",
    mod2_why: "The 'can I touch this?' question in Slack or a stale CODEOWNERS file.",
    mod2_benefit: "Your change on someone else's code travels as a proposal — doesn't block you or invade the owner.",
    mod3_title: "Impact",
    mod3_h3: "What breaks if you change this",
    mod3_what: "Real semantic analysis: AST and reference resolution, not text matching.",
    mod3_why: "Breaking a third party and finding out in CI, in review or in production.",
    mod3_benefit: "Only the affected get notified, in the moment. No spamming the whole team.",
    mod_own_me: "you",
    mod_own_free: "free",
    mod_impact_ok: "automatically notified",

    // Flow
    s03_k: "03 · How it works, live",
    s03_h_1: "Three steps. Inside the editor.",
    s03_h_2: "No PR queue to leave for.",
    s03_sub: "What was once branch → PR → review → merge is now propose → approve → apply. Same safety, no ceremony.",
    flow: [
      {
        n: "01 · YOU EDIT",
        t: "Open the file and write",
        d: "No asking for permission, no waiting for a branch. Live presence shows where everyone is — if you get close to an occupied zone, you see it before touching it.",
        chip: { txt: "no branch · no PR", cls: "" },
      },
      {
        n: "02 · ORUX DETECTS",
        t: "The system cross-checks ownership and impact",
        d: "If the zone has an owner, your change becomes a proposal. If you changed a signature, Orux figures out who actually uses it — only they get notified.",
        chip: { txt: "proposal · impact computed", cls: "wt" },
      },
      {
        n: "03 · IT APPLIES",
        t: "One click from the owner, lands in Git",
        d: "The owner approves with one click. The change appears in everyone's editor instantly and stays as a real Git commit. git clone still gets you the whole project.",
        chip: { txt: "real Git commit · instant", cls: "go" },
      },
    ],

    // Not us
    s04_k: "04 · What we are NOT",
    s04_h_1: "We sell coordination,",
    s04_h_2: "not control.",
    nots: [
      "Not corporate governance, permissions or code surveillance.",
      "Doesn't replace Git, GitHub or your IDE: it's a layer on top.",
      "Doesn't block you before trying — edit first, always.",
      "Not a chatbot glued to an editor.",
    ],

    // FAQ
    s05_k: "05 · Frequently asked",
    s05_h_1: "What teams ask",
    s05_h_2: "before trying it.",
    s05_sub: "Direct answers, no fluff. If one's missing, drop us a line.",
    faq: [
      {
        q: "Does Orux replace Git or GitHub?",
        a: "No. Orux is a layer on top of Git. Each workspace is a real Git repo: commit, push and git clone work as always. GitHub or GitLab stays as the origin — your PRs, issues and Actions live there, not here. If you stop using Orux tomorrow, the repo stays intact.",
      },
      {
        q: "Do I have to switch IDEs?",
        a: "To start, yes: the current version is a web app (editor in the browser). VSCode and JetBrains plugins are on the roadmap — the idea is to bring coordination to your IDE, not force you to abandon it.",
      },
      {
        q: "How does ownership work? Does it block me?",
        a: "It never blocks you. If you touch a zone with an owner, your change travels as a proposal with impact already computed. The owner approves with one click. Edit first, negotiate after. Whoever first touches a file becomes its owner; a workspace admin can reassign when needed.",
      },
      {
        q: "What happens if two people edit the same line?",
        a: "It doesn't happen. Per-line presence reserves the line the moment the first person touches it: the second sees it before typing. We don't use CRDT — the thesis is to prevent, not to merge.",
      },
      {
        q: "What languages does impact analysis understand?",
        a: "Today: Python and JavaScript/TypeScript. The analysis is real (AST and reference resolution), not text matching. More languages as usage scales — no promises we can't keep.",
      },
      {
        q: "What about code privacy?",
        a: "Orux is self-hostable: run your own instance with Docker, your code never leaves your infrastructure. The hosted version on orux.space clones your repo on demand and the Git token is ephemeral — it passes through subprocess env, never stored on disk, in logs or in URLs.",
      },
      {
        q: "Is it for small or large teams?",
        a: "Designed for 2 to 50 devs per team. Free covers up to 5. Above that, Premium adds multi-repo and transitive analysis. Larger teams work, but the sweet spot is 2 to 50.",
      },
      {
        q: "Can I use it offline?",
        a: "No. The thesis depends on shared real-time state. If you lose your network, the editor tells you and stops destructive changes until you reconnect.",
      },
      {
        q: "Is there a real free plan?",
        a: "Yes: up to 5 devs, one workspace, full core (presence + ownership + impact + Git). No trial, no card, no asterisks. You only pay if the team grows or needs multi-repo analysis.",
      },
    ],

    // Audience
    s_aud_k: "Who it's for",
    s_aud_h_1: "Built for three situations",
    s_aud_h_2: "where coordination really hurts.",
    s_aud_sub: "Not a universal tool. It works best when coordination is async, the code still fits in one head and it's not too late to set the flow.",
    aud: [
      {
        t: "Technical founder · 2 to 5 devs",
        d: "You're writing the code and building the team at the same time. Every block costs you an afternoon. Orux removes coordination cost without adding corporate governance.",
        b: ["Workspace in minutes, no governance", "Free forever up to 5 devs", "Optional self-host if the client requires it"],
      },
      {
        t: "Open source starting out",
        d: "Async contributors, no standups, no shared Slack. CODEOWNERS ages badly and CI is where you find conflicts.",
        b: ["Live ownership, not a stale file", "Self-host with Docker, real Git repo", "Visible to newcomers without onboarding meetings"],
      },
      {
        t: "Mid-sized team · 5 to 50 devs",
        d: "The lead no longer remembers who touches what. Knowledge lives in their head and becomes a bottleneck. Orux distributes impact without new meetings.",
        b: ["Knowledge distributed by real usage", "Cross-repo impact in Premium", "Lives alongside your GitHub/GitLab"],
      },
    ],

    // Security / privacy
    s_sec_k: "Security & privacy",
    s_sec_h_1: "Your code doesn't become our problem.",
    s_sec_h_2: "Auditable, self-host and reversible.",
    s_sec_sub: "Orux mounts on top of Git: if you leave tomorrow, the repo is intact. The coordination layer is yours, not held hostage.",
    sec: [
      {
        t: "Self-host with Docker",
        d: "One image, one docker compose up. Your code never leaves your infrastructure. Same binary as the hosted version.",
      },
      {
        t: "Ephemeral Git token, never stored",
        d: "On push, your token flows only through subprocess env. Never on disk, never in logs, never in URLs, never in .git/config. Output scrubbed.",
      },
      {
        t: "Layer over Git, not hostage",
        d: "Each workspace is a real Git repo. git clone is enough. If you drop Orux, you take the full history with one command.",
      },
      {
        t: "No content telemetry",
        d: "We don't read your code to train anything. Impact analysis runs local to the server (yours if self-host). No LLM in the critical path.",
      },
      {
        t: "Open core, auditable",
        d: "The core is open. You can read how we handle tokens, ownership and change propagation. No black box.",
      },
      {
        t: "Reversible in one command",
        d: "Uninstalling Orux is git clone. No trapped data, no weird export, no vendor lock-in. As a layer should be.",
      },
    ],

    // Pricing
    s06_k: "06 · Pricing",
    s06_h_1: "Starting is free.",
    s06_h_2: "You pay when the team grows.",
    s06_sub: "No trial, no card. Full coordination core is in Free forever. What's paid is scale and depth, not basic functionality.",
    free_tier: "Free · forever",
    free_h4: "For the team starting out",
    free_sub: "The full coordination core, not a stripped version. What gets tiered is scale — not the thesis.",
    free: [
      "Up to 5 devs live in one workspace",
      "Deep impact analysis for Python and TypeScript",
      "Live ownership and direct impact · no surprise merges",
      "Self-hosted with Docker · your code in your infra",
    ],
    free_cta: "Try it free",
    pro_badge: "Recommended as you grow",
    pro_tier: "Premium · when it scales",
    pro_h4: "When the team grows",
    pro_sub: "No team caps, languages that compound, impact that crosses repos and always-warm analysis. For when the lead can no longer be the bottleneck.",
    pro: [
      "No team cap · unlimited workspaces per team",
      "Go, Rust, Java and Kotlin with the same depth",
      "Transitive and cross-repo impact · distributed knowledge",
      "Always-warm analysis · no cold-start when you return",
    ],
    pro_cta: "Start free · upgrade when it matters",

    // Final
    final_h2: "Your team already coordinates. Badly.",
    final_sub: "Standups to know what you touched. PRs to discover what you broke. Meetings to move a signature. There's a shorter path — without losing safety.",
    final_cta: "Create your workspace",
    final_ghost: "How it works",
    final_micro: "Free up to 5 devs · no trial · no card · 60 seconds to start.",

    // Sticky mobile CTA
    sticky_label: "Ready when you are",
    sticky_cta: "Create workspace",

    // Footer
    foot_tagline: "Real-time coordination on top of Git · for teams of 2 to 50",
    foot_enter: "Sign in",
    foot_what: "What it does",
    foot_how: "How it works",
    foot_faq: "FAQ",
    foot_price: "Pricing",
    foot_copy: "© 2026 Orux",

    // Lang
    lang_es: "Español",
    lang_en: "English",
  },
} as const;

export type Traducciones = (typeof T)[Lang];
