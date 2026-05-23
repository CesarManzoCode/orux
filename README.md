# Orux

Un editor colaborativo en tiempo real, sobre Git, para equipos que programan rápido sin romperse entre sí.

## Estado actual

Orux está **desplegado y en uso** en [orux.space](https://orux.space). Es un producto multi-equipo: cada equipo tiene su propio workspace aislado (un repositorio git real), con su presencia, ownership, propuestas y análisis. Construido por capas — **33** hasta hoy. **429 tests** en el backend.

Funciona, end to end: registro y login (con OAuth de GitHub), lobby de equipos (crear equipo, invitar por código, unirse), edición colaborativa en tiempo real, presencia por archivo y línea, ownership con edición tentativa y aprobación de un clic, prevención de colisiones, análisis de impacto semántico multi-lenguaje (Python, JS/TS, Go, Rust), integración con Git (estado, commit, clone y push desde la web), un panel de operador, un tutorial guiado que arranca solo la primera vez que un admin entra a un equipo nuevo, y un modelo freemium con cobro por Stripe.

## Despliegue (Docker)

Cuatro contenedores; sólo Caddy se expone a internet:

- **orux** — el servidor WebSocket de sincronización.
- **api** — un proceso aparte (Starlette): consola del operador, callbacks de OAuth, webhooks de Stripe.
- **postgres** — los metadatos: usuarios, equipos, miembros, invitaciones, ownership.
- **caddy** — sirve el frontend estático, termina TLS automático y proxya `/ws` y `/api`.

El contenido de los archivos vive como repositorios git reales —uno por equipo— en un volumen persistente; Postgres guarda sólo metadatos. Coherente con "un `git clone` basta": cada carpeta de equipo es un repo de verdad.

```bash
cp .env.example .env          # configurá tu dominio y credenciales
make up                       # build + levanta los 4 contenedores
make logs                     # seguir logs   |   make down para apagar
```

Con un dominio real apuntando al VPS, Caddy saca el certificado solo. `make` lista todos los atajos. Desarrollo local: `make dev` (server desde `backend/`) + `cd frontend/ide && npm run dev` (el cliente detecta dev y usa `ws://localhost:8765`).

### Cómo está construido

Orux se construyó por capas, una a la vez, cada una con tests desde el primer commit (`git log` tiene la historia completa). La visión y el detalle de cada pieza —presencia, ownership invisible, edición tentativa, prevención de colisiones, análisis semántico, integración con Git— están explicados abajo, en **La idea**.

### Cómo correrlo

El repo está separado en dos raíces (más orquestación en la raíz): el backend Python vive en `backend/`, el frontend en `frontend/`.

```bash
cd backend
pip install -e ".[dev]"
python -m orux.server
```

El cliente del IDE (React) corre con `cd frontend/ide && npm install && npm run dev`. Las pestañas/clientes conectados se sincronizan en tiempo real.

### Tests

```bash
cd backend && pytest
```

### Estructura

- `backend/orux/protocol/` — los mensajes que viajan por WebSocket.
- `backend/orux/state/` — el estado de un equipo: `Document`, `Workspace`, `Roster` (presencia), `Ownership`, `Proposals`, `DiskStorage`.
- `backend/orux/server/` — el servidor WebSocket; `TeamRuntime` (un equipo aislado), el lobby y el handshake.
- `backend/orux/teams/` y `backend/orux/db/` — el dominio de equipos y la persistencia en Postgres.
- `backend/orux/analysis/` — el análisis de impacto semántico (Python, JS/TS, Go, Rust).
- `backend/orux/identity/` — autenticación: contraseñas, tokens de sesión, OAuth con GitHub.
- `backend/orux/git/` — la integración con Git.
- `backend/orux/api/` — la API del operador, OAuth y el billing de Stripe.
- `backend/tests/` — 429 tests de protocolo, estado, análisis, equipos e integración.
- `frontend/ide/` — el cliente React del IDE. `frontend/landing/` — la landing de marketing. `frontend/ops/` — el panel de operador.

---

# La idea

Un editor colaborativo en tiempo real, sobre Git, para equipos que programan rápido sin romperse entre sí.

No reemplaza Git, ni GitHub, ni VSCode, ni ningún IDE. No es otro Replit ni un playground. Es una capa de coordinación: múltiples personas tocan el mismo proyecto sin pisarse, sin ceremonia innecesaria, y sin errores silenciosos.

---

## Tesis

Git entiende archivos, líneas, commits y ramas. Los equipos trabajan con responsabilidades, dependencias, módulos, contratos y coordinación humana.

Branches, PRs, reviews y merges fueron diseñados para escala. Para equipos de 2 a 50 personas es como usar microservicios en una demo: funciona, pero la fricción es desproporcionada al beneficio.

> **Misma seguridad, sin la ceremonia. El sistema sabe, sin que nadie le pregunte.**

No resolvemos un problema nuevo. Hacemos lo mismo que el flujo actual, marginalmente mejor, de una forma que se nota todos los días.

---

## El dolor

Lo que el dev dice cuando se queja:

- "Tuve que crear una branch para cambiar dos líneas."
- "No sabía que alguien ya estaba tocando eso y ahora hay conflicto."
- "El PR lleva 3 días esperando review y está bloqueando todo."
- "Rompí algo de otro módulo sin darme cuenta."
- "Tuve que preguntar en Slack si podía tocar ese archivo."
- "¿Cómo sé que mi nuevo módulo no rompe nada?"
- "¿Cómo sé si alguien ya implementó esa tarea?"

Y el líder del equipo: **es el cuello de botella porque es el único con la visión completa.** Todo pasa por él. El sistema distribuye ese conocimiento automáticamente.

---

## Origen

La idea nació entrando a un grupo de colaboración open source y notando el flujo real:

1. Hay un tablero con tareas.
2. Alguien agarra una tarea y la ejecuta.
3. Hace un PR.
4. Aparecen preguntas que nadie puede responder fácilmente:
   - ¿Mi código rompe algo que ya existe?
   - ¿Alguien ya implementó algo relacionado que yo no vi?
   - ¿Cómo sé que mi cambio es integrable al estado actual del proyecto?

El líder es el único que podría responder. Ese modelo no escala.

---

## Qué vende el producto

No vendemos ownership, enforcement, control ni governance. El ownership es la implementación interna: el diferencial de un coche. Nadie compra un coche por el diferencial, pero sin él el coche no dobla bien.

Vendemos el resultado que el dev siente:

> **"Toca lo que necesites. El sistema se encarga de que nada se rompa."**

---

## Cómo funciona

### Estado compartido en tiempo real

No hay modo offline. Todos ven el mismo estado del proyecto en vivo. Cada dev ve dónde están trabajando los demás. Como Replit, pero para proyectos reales de producción.

### Ownership invisible

Se pueden asignar responsabilidades sobre archivos, directorios, clases, funciones, módulos, componentes, APIs internas y contratos de datos. La clase `User` le pertenece a Joaquín. El directorio `auth/` le pertenece a un equipo. Un módulo compartido puede tener owners principales y secundarios.

El dev no piensa en quién owns qué. El sistema lo sabe y actúa.

### Edición tentativa

Un dev puede entrar a cualquier parte del código y modificarla. Si esa parte tiene un owner, los cambios son provisionales:

- aparecen visualmente marcados;
- se ven como un diff;
- muestran líneas agregadas, eliminadas y modificadas;
- se comportan como un PR inline;
- no se aplican realmente hasta aprobación.

Cuando el dev guarda, el owner recibe una notificación. Ve el diff y acepta o rechaza con un clic. Botón verde o rojo. Sin formularios, sin workflows pesados.

> **Editar primero. Negociar después. Aplicar al final.**

### Prevención de colisiones

Cuando dos personas van a tocar la misma zona:

- El owner tiene preferencia.
- Si ambos son owner o la zona no tiene owner, el que la tocó primero escribe.
- Nunca dos personas al mismo tiempo en la misma línea.

No se resuelven conflictos después. Se previenen antes.

### Análisis semántico automático

Cuando alguien modifica una clase, función o módulo, el sistema detecta automáticamente dónde se usa ese símbolo en todo el proyecto.

Si Joaquín cambia la clase `User`, el sistema detecta que `User` se usa en `Billing`, `Auth`, `AdminDashboard`, `MobileAPI`, DTOs, tests, serializadores, factories y API handlers. Y notifica a los owners de esas áreas.

Sin clickear un botón. Literalmente lo hace solo.

### Notificaciones a owners

El owner recibe:

- qué cambió;
- quién lo cambió;
- qué archivos se ven afectados;
- si rompe contratos o dependencias;
- qué acción se requiere.

### Integración con Git

Todo vive sobre Git. Un `git clone` basta. Commits, branches, push, pull, PRs y merges siguen existiendo. La herramienta es una capa, no un reemplazo.

---

## Contratos de código

El sistema distingue tipos de cambio:

- **Internos:** no notifican ni bloquean. Variable privada, refactor interno.
- **De contrato (breaking):** pueden requerir adaptación obligatoria. Campo requerido nuevo, eliminar método público, cambiar firma.
- **Non-breaking:** solo notifican. Campo opcional, método nuevo no requerido.
- **Deprecated:** advierten, no bloquean.

Las reglas son configurables por equipo. No todo cambio bloquea todo.

---

## Vista por usuario

Cada dev ve gráficamente:

- qué archivos son suyos;
- qué carpetas le pertenecen;
- qué clases o funciones owns;
- qué cambios pendientes tiene;
- qué propuestas necesita revisar;
- qué dependencias están rotas;
- qué archivos relacionados necesita ver.

Se pueden ver archivos ajenos si hay dependencia afectada o si el equipo configura visibilidad amplia. No es ocultamiento rígido, es reducción de ruido.

---

## Principios

1. Vive totalmente ligada a Git.
2. No reemplaza Git.
3. No obliga a migrar repositorios.
4. No usa formato propietario que atrape el código.
5. Un `git clone` basta.
6. El usuario puede usar el workflow completo o solo la capa opcional.
7. Si quiere pushear directo a `main`, puede.
8. No obliga a adoptar approvals, ownership o enforcement.
9. Todo es opcional, progresivo y no invasivo.
10. La herramienta ayuda, no controla.
11. No se siente como governance corporativo, sino como live collaborative review.
12. La percepción correcta: "misma vida, menos dolor".
13. El editor es vehículo; el núcleo es la coordinación semántica.
14. No hay modo offline. El estado compartido en tiempo real es la base.

---

## Orden de construcción

Por capas, cada una depende de la anterior:

1. **Estado compartido del proyecto en tiempo real** — la capa cero.
2. **Edición en tiempo real** — sobre el estado compartido.
3. **Ownership** — asignación de responsabilidades.
4. **Análisis semántico** — detección automática de impacto.
5. **Notificaciones a owners** — aviso cuando un cambio impacta código owned.
6. **Integración con Git** — commits, push, pull, branches, PRs desde la herramienta.

No se añade una capa hasta que la anterior funcione.

---

## Plataforma

**Fase 1: Web app.** Rápida de construir y validar. Permite encontrar equipos sin fricción de entorno.

**Fase futura: nosotros vamos a su entorno.** Plugin de VSCode, JetBrains, lo que haga falta. No obligamos al dev a venir a nuestro editor; llevamos el producto a donde ya está.

---

## Público

**Early adopters:** equipos nuevos sin inercia, proyectos open source que empiezan, estudiantes que colaboran, founders técnicos con 2-3 personas.

**Sweet spot:** startups de 5 a 50 devs, equipos open source medianos, equipos fullstack rápidos, agencias técnicas, equipos remotos o híbridos con módulos compartidos.

**No es para:** enterprise grande con compliance, monorepos masivos, CODEOWNERS, CI sofisticado. Tampoco para 1-2 devs donde no hay fricción.

**Quién decide adoptar:** el líder del equipo (CTO, tech lead, founder técnico).

---

## Posicionamiento

**Vendemos:** colaboración segura, velocidad sin riesgo, live review, safe refactors, instant approvals, menos fricción, menos mensajes en Slack/Discord, menos PRs gigantes, menos conflictos, menos miedo a tocar código, menos bugs por cambios de contrato.

**No vendemos:** permisos, enforcement, control, vigilancia, governance, microgestión de código.

### Framing

> "Crear branches para proyectos de un par de devs es como usar microservicios en una demo."

> "Toca lo que necesites. El sistema se encarga de que nada se rompa."

> "Sin siquiera clickear un botón, literalmente lo hace solo."

> "Multiplayer semantic coding."

> "Un editor colaborativo en tiempo real para equipos que programan rápido sin romperse entre sí."

---

## Feature estrella del onboarding

En los primeros 10 minutos, el usuario debe experimentar:

**Cambiar una clase o función, y en automático ver exactamente qué archivos necesitan cambio y que se notifique a los owners.**

Antes: tenía que recordar dónde estaba esa función y qué código ajeno la usaba.
Ahora: todo se hace solo. Solo queda aprobación e implementación.

---

## Riesgos

1. **Feature soup.** Construir 20 features mediocres en vez de 1 workflow increíble. Mitigación: capas, una a la vez.
2. **Análisis semántico multi-lenguaje es muy difícil.** JetBrains lleva décadas. Empezar con un solo lenguaje y soportarlo bien.
3. **La competencia real es la inercia.** Terminal, PRs, branches, Slack. "Suficientemente bien" mata startups.
4. **Ownership puede generar territorialismo.** Diseñar para colaboración, no para feudos. Ownership invisible.
5. **Cool pero no indispensable.** La validación correcta: equipos no quieren dejarlo de usar.
6. **Optional-first puede diluir adopción.** Si todo es opcional, algunos lo usan inconsistentemente y se pierde valor de red.
7. **Coordinación no siempre se arregla con tooling.** A veces el problema es arquitectura, comunicación, documentación o cultura.
8. **Un editor en tiempo real con análisis semántico es de lo más difícil de construir.** Capas incrementales.

---

## Diferenciación

| Herramienta | Qué hace | Qué no hace |
|---|---|---|
| Git/GitHub/GitLab | Branches, PRs, merges, CODEOWNERS, CI | No previene colisiones, no detecta impacto semántico en tiempo real |
| Replit | Edición en tiempo real, deploy rápido | No es para producción, Git integration deficiente, sin ownership |
| Gitpod/CodeSandbox | Entornos de desarrollo remotos | No colaboración en tiempo real, no análisis semántico |
| JetBrains | Análisis semántico profundo, refactors | Individual, no colaborativo, no coordinación de equipo |
| VSCode Live Share | Edición colaborativa | No ownership, no análisis semántico de impacto, no prevención de colisiones |

Lo que no existe en ninguna: **estado compartido en tiempo real + ownership invisible + análisis semántico de impacto + edición tentativa + aprobaciones de un clic, todo sobre Git.**
