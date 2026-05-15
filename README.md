# laidea

Un editor colaborativo en tiempo real, sobre Git, para equipos que programan rápido sin romperse entre sí.

## Estado actual: capa 5 — prevención de colisiones

Si un archivo **no tiene dueño**, ya no se pisan: antes de aplicar un cambio, el servidor mira (vía presencia) si alguna línea que tocas la está ocupando otro presente. Si sí, **rechaza tu cambio y te devuelve el contenido real** — "nunca dos personas a la vez en la misma línea, el que la tocó primero escribe". El **dueño tiene preferencia**: a él el lock no le aplica. Cero CRDT: se previene, no se fusiona. (Para no bloquear de más, el servidor distingue una línea *modificada* de una que solo *se desplazó* por una inserción.)

### Capa 4 — ownership

Un archivo puede tener **dueño** (quien lo crea lo es, sin botón). Si lo edita alguien que no es el dueño, su cambio **no se aplica**: se convierte en una **propuesta** que le llega al dueño, que la **aprueba o rechaza con un clic** (ve el diff por líneas, botón verde o rojo). Si aprueba, converge todo el mundo; si rechaza, al autor se le revierte.

Andamiaje del prototipo: identidad anónima pero **estable por token** (el cliente guarda un token en `localStorage`; recargar la página conserva tu identidad y tu ownership). No es auth real todavía. Como la identidad sobrevive al reload, el ownership ya no se libera al desconectar.

### Capa 3 — persistencia

El workspace **sobrevive a reiniciar el servidor**. Al arrancar, el server lee los archivos de un directorio en disco (`~/.laidea/workspace` por defecto —fuera del repo a propósito, para no disparar el auto-reload de servidores estáticos que vigilan la carpeta—, o `LAIDEA_DATA`); cada edición se escribe ahí. Sin historial ni versiones todavía. Los paths que llegan del cliente se validan contra *path traversal* antes de tocar el disco.

### Capa 2 — presencia

Cada quien ve **dónde está trabajando el resto**. Al conectar, el servidor asigna una identidad anónima (color + nombre tipo `anónimo-3`; sin login todavía). El sidebar muestra con puntos de color quién tiene abierto cada archivo, y dentro del archivo abierto se ve, sobre la línea exacta, en qué línea está escribiendo cada persona. Cuando alguien se desconecta, su marcador desaparece.

Presencia por archivo + número de línea (no posición de caracter): es lo que responde "¿alguien ya está tocando esto?" sin la fragilidad de superponer cursores sobre un `<textarea>`.

### Capa 1 — múltiples archivos (base)

Sincronización de un **workspace** completo entre múltiples clientes en tiempo real. Cada cliente ve la lista de archivos, puede crearlos, abrirlos y editarlos. Las ediciones se propagan a todos los demás conectados sin pisarse entre archivos distintos.

### Cómo correrlo

```bash
pip install -e ".[dev]"
python -m laidea.server
```

Luego abre `web/index.html` en dos o tres pestañas del navegador y escribe en una. Las demás se sincronizan.

### Tests

```bash
pytest
```

### Estructura

- `laidea/protocol/` — mensajes que viajan por WebSocket (Init, Update, Welcome, Presence, Leave, Claim, Ownership, Proposal, Resolve).
- `laidea/state/` — modelo del estado: `Document`, `Workspace`, `Roster` (quién está y dónde), `DiskStorage` (persistencia), `Ownership` (dueño por path), `Proposals` (cambios tentativos) y `lineas_tocadas` (diff LCS para el lock por línea).
- `laidea/server/` — servidor WebSocket de sincronización.
- `web/` — cliente HTML con árbol de archivos + textarea.
- `tests/` — tests de protocolo, estado e integración.

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
