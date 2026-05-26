# Lanzamiento Show HN — Plan completo

> Hoy: **martes 26 de mayo 2026, 14:15 Guadalajara**.
> Tu zona: **CST México (UTC−6)**. New York está en **EDT (UTC−4)** → 2h adelante.

---

## 1) Cuándo publicar

**Recomendación: miércoles 27 de mayo, 7:30am Guadalajara** (= 9:30am EDT).

- HN se gana en las primeras 2h. El "prime time" es 8–10am EDT, cuando devs de EE.UU. abren la primera pestaña del día. 7:30am GDL cae justo en ese pico.
- Miércoles es estadísticamente el mejor día para Show HN (lunes está saturado, viernes está vacío).
- Te deja **~17h para terminar prep** (resto de hoy + noche).

**Alternativa si necesitás más prep: jueves 28 de mayo, 7:30am Guadalajara.**

**No publicar:**
- Viernes/sábado/domingo (HN vacío de devs).
- Lunes (saturado por todo lo que se acumuló del fin de semana).
- Antes de 7am GDL (frontpage europeo, no es tu audiencia primaria).
- Después de 10am GDL (= 12pm EDT, ya pasó el pico matutino).

---

## 2) Checklist pre-publicación (hacer hoy y mañana antes de las 7am)

### Producto
- [ ] Smoke test del demo embed en **Safari macOS**, **Safari iOS**, **Firefox**, **Chrome Android**. El iframe del hero (`/app/?demo=1`) es lo primero que ve el visitante; si se rompe en algún motor mainstream, perdés el post.
- [ ] Verificar que el flow de signup gratuito completa en **<60s** (lo prometés en la landing).
- [ ] `htop` en el VPS: confirmar que las 4 CPUs / 8GB están sanas y hay holgura. Show HN puede traer 5–50k visitas en 24h.
- [ ] Confirmar que `mailto:cesarmanzocode@gmail.com` funciona desde la landing y que vas a leer ese inbox cada 30 min durante las primeras 24h.
- [ ] Confirmar que `https://orux.space/api/v1/status` responde — un dev curioso lo va a tocar.
- [ ] Dejar un terminal abierto con `make logs` para ver tráfico en vivo (no para debugging — para sensación de qué tan grande es el spike).

### Cuenta de HN
- [ ] Tu cuenta `news.ycombinator.com` debe tener **>10 karma**. Si es nueva (0 karma), el post baja casi automático. Si necesitás karma rápido: hacé 2–3 comentarios útiles en posts de hoy/mañana antes de lanzar (no spam — comentarios reales en posts donde tengas algo que aportar).
- [ ] Verificar que el email de la cuenta HN está confirmado.

### Soporte humano
- [ ] Bloqueá **24–48h** post-publicación para responder comentarios. La presencia del autor multiplica engagement por 3–5x. Si publicás y desaparecés 4h, el post muere.
- [ ] Avisale a 2–3 amigos/familia que vas a publicar — **NO les pidas upvote** (HN detecta voting rings y te baja el post). Solo: "voy a publicar mañana 7:30am, si lo ves orgánicamente, comentá si te interesa".
- [ ] Tené tu teléfono con notificaciones de HN replies (la app `Hacker News` para iOS/Android funciona).

---

## 3) El post de Show HN

### Título (3 opciones, marcado el recomendado)

1. ✅ **`Show HN: Orux – A real-time coordination layer on top of Git`**
2. `Show HN: Orux – Preventing merge conflicts in real time, not resolving them`
3. `Show HN: Orux – Real-time multiplayer editing over Git for small teams`

**Por qué la #1:** sobrio, descriptivo, sin hype. HN aprecia eso. La #2 es más opinionated (puede atraer más clicks pero también más pushback inicial). La #3 limita audiencia al decir "small teams" en el título.

**NO incluir "built at 16" / "by a teenager" en el título** — HN castiga clickbait basado en identidad. Va en el body, donde sí pega.

### Body (copiar tal cual, en inglés)

```
Hi HN — I'm Cesar, the solo dev behind Orux.

Orux is a real-time coordination layer on top of Git for teams of 2 to 50 devs. Per-line presence, live ownership, and semantic impact analysis — resolved before the merge, without replacing GitHub, GitLab, or your IDE.

The premise: branches, PRs, reviews, and merges were designed for scale. For small/medium teams they work, but the friction is disproportionate to the benefit. A conflict isn't avoided by reviewing harder; it's avoided by seeing it as it happens.

What Orux does, today, in production:

- Per-line presence — you see who's editing where, before you type.
- Implicit ownership — derived from real usage, persisted across sessions. Your change on someone else's code travels as a proposal; nothing ever blocks you.
- Semantic impact analysis (Python, JS/TS, Go, Rust) — change a signature and only the callers that actually use it get notified. AST/tree-sitter + LSP fan-out, not text matching.
- Real Git underneath — each workspace is a real Git repo, `git clone` is enough. PRs, push, GitHub stay where they are.

Decisions I made on purpose:

- No CRDT. The thesis is to prevent collisions, not merge them after the fact. Per-line presence reserves the line on first touch.
- No LLM in the critical path. The product works because of structural analysis, not because it asks a model.
- No governance/permissions/enforcement. Owners get one-click approvals; nothing is blocked.

Things it doesn't do yet (and the landing makes this explicit):

- It's a web app. VSCode/JetBrains plugins are on the roadmap, not today.
- Not compiler-grade type resolution. AST + LSP fan-out covers ~80% of the daily flow; the deep cross-module resolution JetBrains spent 20 years on is deferred.
- Built solo by 1 person — I'm 16, no team, no VC. Bugs reported during the day get answered the next day, not in 2 hours. No 24/7 support theatre.

Stack: Python 3.11 backend (websockets, asyncpg, tree-sitter, pyright), React + TypeScript frontend, Postgres for metadata, real Git repos per team on disk. Deployed on a $48/mo DigitalOcean droplet. 478 backend tests; layered build (33 layers), tests from the first commit of each layer.

Try it: https://orux.space — free up to 5 devs, no card, no trial. The link drops you into the web app in ~60s.

Happy to answer anything about the architecture, the decisions, why it's not open source yet, or how I'm thinking about the business. AMA.
```

**Por qué este body funciona:**
- Primer párrafo: qué es, una frase.
- Segundo: tesis defendible (CRDT/PR/merge debate).
- Bloque de bullets concretos (HN escanea, no lee párrafos largos).
- "Decisions I made on purpose" — gente de HN ama saber qué dijiste NO.
- "Things it doesn't do yet" — desarma escépticos antes de que empiecen a atacar.
- "I'm 16" aparece UNA vez, sin drama, en el lugar donde refuerza credibilidad ("solo, no equipo, no VC").
- Stack al final — HN ama el stack, pero después del pitch.
- "AMA" cierra invitando.

---

## 4) Primer comentario — el "seed comment"

**Cuándo postearlo:** **3–5 minutos después del post**, desde la misma cuenta. Esto siembra discusión técnica y te ancla como autor presente.

**Qué postear** (en inglés, copiar tal cual):

```
Seeding a controversial decision in case anyone wants to dig in:

I deliberately did NOT use CRDT for the real-time editing layer. Most multiplayer editors (Figma, Replit, Live Share) lean on CRDT to merge concurrent edits after the fact — it's elegant when the goal is "two people typing in the same paragraph."

For code, I think that's the wrong default. A merged-CRDT result is still a merge: somebody's intent gets reordered by an algorithm, and code is the worst place for "the algorithm picked the wrong winner." The bug appears two commits later, in CI, far from where it was caused.

Orux's thesis is to prevent the collision instead: per-line presence reserves the line the moment the first person touches it, and the second sees it before typing. No merge to inspect later because there was no concurrent write.

Trade-off I'm aware of: this only works because the state is shared in real time. There's no offline mode, by design. If you lose your network, the editor tells you and stops destructive changes until you reconnect.

Curious what people who've shipped CRDT in production (or fought it) think about this framing.
```

**Por qué este comment funciona:**
- Es opinionated y técnico — exactamente el tipo de seed que HN debate.
- Reconoce el trade-off (no offline) sin esconderlo.
- Invita a una audiencia específica ("people who've shipped CRDT") — esa gente se siente llamada a responder.
- No es defensivo, es framing.

---

## 5) Respuestas pre-redactadas a comentarios típicos

Tener estos guardados en notas para copy-paste rápido. **NO los postees todos** — solo cuando alguien pregunte algo similar. Adaptar a cada comentario específico (no respondas robóticamente).

### Q1: "Why not open source?"

```
Fair question, gets asked every time.

Short version: Orux is a SaaS, not an open-core product. The coordination state (ownership, presence, proposals) lives on the server by necessity — that's where the real-time guarantee comes from. The code I'd open-source is the analysis pipeline and the protocol, which is also the moat. Opening it today, alone, without a team to maintain forks or review PRs from strangers, would be a worse outcome than keeping it closed and shipping.

What I optimized for instead: your code stays in your Git repo. A `git clone` is enough to walk away. The coordination layer is mine while you use it; the code is yours always. That's the reversibility guarantee I can actually keep at this stage.

Open-sourcing parts of it (protocol, AST analyzers) is something I'd revisit when there's a team and the product has product-market-fit. Not today.
```

### Q2: "How is this different from VSCode Live Share / Cursor multiplayer / JetBrains Code With Me?"

```
Live Share / Code With Me are pair-programming sessions: one person opens their editor, others join, the session dies when they close. There's no shared Git state, no persistent ownership, no asynchronous coordination across days.

Orux is the team's permanent workspace. Async by default. You log in tomorrow and the ownership of files, pending proposals, and presence history are all where you left them. The Git repo is real and persisted server-side, not piggybacking on one person's local checkout.

Cursor's multiplayer (when it ships) and Replit are closer in spirit, but neither does semantic impact analysis (change a signature → notify only the actual callers) or ownership derived from real usage. They're collaborative editors; Orux is a coordination layer that happens to come with an editor.
```

### Q3: "Bus factor — what happens if you stop maintaining it?"

```
Honest answer: today, the bus factor is 1. That's a real risk and I won't pretend otherwise.

What I can do about it at this stage:
- The repo per team is a real Git repo on disk. If Orux disappears tomorrow, every team can `git clone` their workspace from their last sync (and they already have their GitHub origin anyway). They lose coordination state — ownership, proposals — but they don't lose code.
- Postgres backups run nightly to off-site storage.
- The product has been deployed and stable for weeks; the code is layered (33 layers, 478 tests), so onboarding a future maintainer wouldn't start from zero.

What I can't do: pretend I have an SLA. If you're shipping safety-critical software with a 50-person team, Orux isn't ready for you yet. The early adopters I'm aiming for (2–5 dev side projects, technical cofounders) understand the trade-off.
```

### Q4: "What about my code privacy? It runs on your VPS?"

```
Yes, and that's a real concern post-Cursor-incident. Here's the actual model:

- When you sign in and pick a team, Orux clones your repo on demand into an isolated per-team workspace on the server. That's the working copy the editor talks to.
- The Git token you provide for `push` flows only through subprocess env. Never written to disk, never logged, never embedded in URLs, never in `.git/config`. Subprocess output is scrubbed before logging.
- No content telemetry. Your code isn't read to train anything. No LLM is on the critical path of the product.
- Per-team isolation is hard: presence, broadcasts, ownership state — a connection literally cannot see another team's data, enforced at the runtime level (each team has its own `TeamRuntime`).
- I run on a $48/mo DigitalOcean VPS in their default datacenter. No fancy compliance theatre, but also no third-party trackers, no Google Analytics, no Plausible. Telemetry endpoint is mine.

If your threat model is "code can't leave my laptop", Orux isn't for you — neither is GitHub. If it's "I trust GitHub but want shorter feedback loops", the trust delta is small.
```

### Q5: "Why no VSCode plugin yet?"

```
Order of operations. The web app forced me to build the coordination layer end-to-end without leaning on a host IDE's quirks. A VSCode plugin that ships with half the coordination semantics would feel worse than a web app that ships with all of them.

Now that the coordination layer is solid, the plugin is mostly transport translation (LSP-style messages from VSCode to the same server, instead of WebSocket from the web client to the server). It's on the roadmap. It is genuinely not built today; I'm not hiding it behind "soon".
```

### Q6: "What about big monorepos / 50+ devs / enterprise?"

```
Not the target today, by design.

The sweet spot is 2–50 devs per team. The product was built for the friction-rich, small-team case — where PR ceremony is disproportionate, where the lead is a bottleneck, where the cost of coordinating eats a meaningful slice of the week. Above 50 devs, you're in CODEOWNERS / SOX / compliance territory, and you actually want the ceremony Orux removes.

Big monorepos break the impact analysis assumption (analyzing the whole repo on every save doesn't scale). I have an idea for incremental analysis (per-symbol caching, only re-run on changed dependency graphs), but I haven't built it and won't until a user has the problem.

I'd rather be the right tool for 100 small teams than a bad tool for 5 big ones.
```

### Q7: "How does the per-seat pricing work for a 2-person team?"

```
Two-person teams are free forever. Free is up to 5 devs in one workspace with the full core (presence + ownership + impact + Git). No trial, no card, no asterisks — pricing was designed so the early team that built around Orux doesn't get squeezed when it grows from 2 to 4.

Above 5 devs, or if you want multi-repo / transitive impact / cross-repo notifications, that's $5/seat/month (beta pricing — explicitly adjustable based on feedback). One seat per member, like ChatGPT Business. If you have 7 devs, you're paying for 7 seats. When someone leaves, the quantity adjusts.

The price is beta and I'm honest about that. Email me if it's blocking adoption; I'd rather hear it now than after I lock it in.
```

### Q8: "Can I self-host?"

```
Not today. The product is a SaaS. The deployment is Dockerized (4 containers: WS server, HTTP API, Postgres, Caddy) and I could in theory hand you the compose file, but I don't ship self-host because:

1. Coordination state is the part I can guarantee — if your self-hosted instance corrupts, I can't help you.
2. Updates and migrations are continuous; self-host would mean either pinning versions (and shipping security holes) or a release cadence I can't sustain solo.

If your reason for wanting self-host is "code can't touch external servers", I'd rather you not use Orux than use it stressed. If your reason is "I want to inspect what's running", I'm open to giving access to a read-only deployment for technical due diligence on a case-by-case basis.
```

### Q9: "What languages does it support beyond the ones listed?"

```
Today: Python, JavaScript/TypeScript, Go, Rust — all with real analysis (AST or tree-sitter, LSP fan-out via pyright, typescript-language-server, gopls, rust-analyzer). For unsupported languages, the analyzer degrades gracefully to a regex tier that still catches the obvious cases (renamed function, same name across files) but doesn't do scope resolution.

Java and Kotlin are next — the architecture is per-language analyzers, so adding one is mechanical (parser + symbol extractor + LSP wrapper). I haven't shipped them because I don't have a user asking for them yet. If you'd actually use it, tell me and I'll prioritize.

Long term, anything with a mature LSP and a tree-sitter grammar is a candidate. C/C++ is harder because of the include model.
```

### Q10: "What does the demo show? It loaded but I'm not sure what I'm looking at."

```
The hero embeds the actual IDE running in demo mode (`?demo=1`). What you're seeing is a scripted loop of two clients (Tomas as owner, Ana as proposer):

1. Ana edits the signature of `claim()` in `sync.py`.
2. Orux detects that 4 places use `claim()` (the impact card lists them).
3. Ana's edit becomes a proposal on Tomas's side (because he owns the file).
4. Tomas approves with one click; the change becomes a real Git commit and sync indicator updates.

The PIP (Picture-in-Picture) bottom-right is Ana's self-view in a separate iframe — proof that it's two real clients running, not a video. If you want to play with it yourself, the main CTA drops you into the real product with a free workspace.
```

---

## 6) Durante las primeras 48h

### Hora 0–2 (la ventana crítica)
- Refrescar HN cada 5–10 min los primeros 30 min.
- Si entra a `/newest` y sube a `/show`, vas bien. Si en 30 min sigue en `/newest` con 0–1 upvotes, no va a despegar (no es fracaso, es la realidad de HN — el 80% de los posts no pegan).
- Responder cada comentario en **<30 min**. Aun si la respuesta es "great question, let me think and reply tonight."

### Hora 2–24
- Responder en **<2h**. Si vas a dormir, postea un comentario público diciendo "going to sleep, I'll catch up in 6h, keep the questions coming" — gente lo respeta y sigue comentando.
- Si reportan un bug, **hot-fix y mencionalo en el thread**. "Fixed in production, thanks for reporting" en HN vale oro.
- NO te enojes con los críticos. Aun los duros. Cada respuesta defensiva mata el post.

### Hora 24–48
- Comentarios bajan en frecuencia. Responder igual con cuidado, ya bajaste de frontpage si pegaste.
- Mirá métricas: signups, retención del demo, errors reportados a `/api/v1/errors`. Eso es el verdadero ROI del Show HN, no los puntos.

### Días 3–7
- Hilo post-mortem mental: ¿qué preguntas se repitieron? Esas van a la FAQ de la landing.
- Si alguien te contactó por email para Premium, **responder en <24h** mientras todavía es candidato cálido.

---

## 7) Señales de éxito vs fracaso

### Hit (60–80 puntos o más, frontpage 6+ horas):
- 100–500 signups gratuitos.
- 2–5 emails para Premium / activación.
- 1–3 menciones en Twitter de gente con audiencia técnica.
- ~10 bug reports reales (eso es bueno, no malo).

### Discreto (15–40 puntos, /show pero no frontpage):
- 30–100 signups.
- 0–1 email Premium.
- Útil como validación, no como tracción. Replantear y repetir en 3–6 meses con nuevo ángulo.

### Flop (<10 puntos, muere en /newest):
- 10–30 signups orgánicos.
- No es catastrófico. HN es un canal, no el canal. El 80% de los Show HN no despegan. Volvés a intentar con otro ángulo cuando tengas un milestone nuevo (capas adicionales, casos de uso reales documentados, etc.).

---

## 8) Después del lanzamiento

- **No re-lanzar Show HN en <3 meses** — HN no quiere ver el mismo producto dos veces sin un cambio sustancial. La próxima vez puede ser: "Show HN: Orux ahora con plugin de VSCode" o "Show HN: 6 meses construyendo Orux, lo que aprendí".
- **Mover los emails de signup a una secuencia simple** — sin spam, solo: día 1 "gracias", día 7 "¿qué tal?", día 30 "¿seguís usando? feedback?".
- **Post-mortem en tu blog/Twitter** una semana después — qué números reales, qué aprendiste. Eso a veces pega más que el Show HN original.

---

## TL;DR — qué hacer en orden

1. **Hoy martes hasta dormir:** smoke test cross-browser, verificar VPS, terminar lo que te falte del checklist.
2. **Mañana miércoles 7:00am GDL:** despertarte, café, último smoke test al demo.
3. **7:30am GDL exacto:** copiar título + body al formulario `news.ycombinator.com/submit`. Verificar URL = `https://orux.space`. Submit.
4. **7:33am GDL:** abrir tu propio post, copiar el "seed comment" sobre CRDT.
5. **Las siguientes 12h:** responder TODO comentario. Usar las respuestas pre-redactadas como base, adaptar.
6. **Mañana noche:** dormir si bajó la frecuencia. Postear "going to sleep, back in 6h".
7. **Jueves mañana:** segunda vuelta de comentarios.
8. **Viernes:** post-mortem de números. Email a quien preguntó por Premium.

**Suerte. Si todo sale mal, no es el fin — es data. Si sale bien, prepará el VPS para más tráfico antes del día siguiente.**
