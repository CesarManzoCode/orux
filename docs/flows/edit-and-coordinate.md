# Flow: Edición coordinada

El corazón del producto. Cómo dos devs editan el mismo workspace sin pisarse, y cómo se resuelve cuando uno toca el archivo de otro.

## Caso 1: Editar archivo sin dueño

```
Ana (cliente)         Server WS                       Workspace + Ownership
─────────             ─────────                       ─────────────────────
  │                       │                                    │
  │── Update ────────────→│                                    │
  │   {path: "x.py", c}   │                                    │
  │                       │ ownership.owner("x.py") → None     │
  │                       │ workspace.exists("x.py") → False   │
  │                       │ (es nuevo)                         │
  │                       │── workspace.update("x.py", c) ────→│
  │                       │── ownership.claim("x.py", ana) ────→│
  │                       │← ownership_store.guardar() ───────│
  │                       │                                    │
  │←──── Update ──────────│ (a todos menos Ana)                │
  │   {path, content}     │                                    │
  │←──── Ownership ───────│ (a todos)                          │
  │   {owners: {x.py: ana}}│                                   │
```

**Regla "el que crea es dueño"**: la primera vez que se ve un path es porque alguien lo está creando. Ese alguien queda como dueño automáticamente, sin botón.

## Caso 2: Editar tu propio archivo

```
Ana                   Server                         Workspace
───                   ──────                         ─────────
  │── Update ────────→│                                  │
  │   {x.py, c'}      │                                  │
  │                   │ ownership.owner("x.py") → "ana"  │
  │                   │ (sos vos)                        │
  │                   │── workspace.update(x.py, c') ────→│
  │                   │                                  │
  │←── Update ─────────│ (a todos menos vos)             │
```

Directo. Sin coordinación necesaria — sos dueño.

## Caso 3: Editar archivo de otro

```
Beto                  Server                  Workspace + Proposals      Ana (dueña de x.py)
────                  ──────                  ─────────────────────       ───────────────────
  │                       │                              │                       │
  │── Update ────────────→│                              │                       │
  │   {x.py, c''}         │                              │                       │
  │                       │ ownership.owner(x.py) → "ana"│                       │
  │                       │ (Beto no es Ana)             │                       │
  │                       │                              │                       │
  │                       │── proposals.put(            │                       │
  │                       │     path=x.py,              │                       │
  │                       │     author=beto,            │                       │
  │                       │     content=c'') ───────────→│                       │
  │                       │← Proposal{id="x.py::beto"} ─│                       │
  │                       │ ← proposals_store.guardar() │                       │
  │                       │                              │                       │
  │                       │── Proposal ────────────────────────────────────────→│
  │                       │                              │   {proposal: {...}}   │
```

El archivo en el workspace **NO se modifica**. Beto NO ve su cambio aplicado. Lo único que sucede es que su content queda registrado como propuesta tentativa pendiente, y Ana recibe un aviso.

### ID determinista de la propuesta

`id = "x.py::beto"`. Si Beto sigue tipeando, sus updates reemplazan la propuesta en vez de acumular. Ana siempre ve la versión más reciente del cambio propuesto.

### Reentrega si Ana está offline

Si Ana no está conectada al recibirse la propuesta, queda en `Proposals` (y en Postgres si hay store). Cuando Ana entra (handshake del equipo), el server hace:

```python
pendientes = rt.proposals.para(ana_id, rt.ownership.owner)
for prop in pendientes:
    await server._enviar_a(rt, ana_id, encode(ProposalMessage(proposal=prop)))
```

Ana ve todas las propuestas pendientes para archivos que le pertenecen.

## Caso 4: Ana resuelve la propuesta de Beto

### Aprueba

```
Ana                   Server                       Workspace + Proposals
───                   ──────                       ─────────────────────
  │                       │                                │
  │── Resolve ───────────→│                                │
  │   {prop_id, accept=T} │                                │
  │                       │ resolve_use_case:              │
  │                       │   proposals.pop(prop_id)       │
  │                       │   proposals_store.borrar()     │
  │                       │   viejo = workspace[x.py]      │
  │                       │── workspace.update(x.py, prop.content) ─→│
  │                       │                                │
  │←── Update ────────────────────────────────→ (a todos)
  │   {x.py, prop.content}                                 │
  │                                                        │
  │                       │── notificar_impacto(           │
  │                       │     rt, x.py, viejo, nuevo,    │
  │                       │     beto_id, "Beto") ──────────→│
  │                       │   (dispara análisis semántico) │
```

El update se aplica al workspace, se difunde, y se dispara el análisis de impacto **como si Beto lo hubiera podido aplicar directo**. Si el cambio afecta `auth.py` que es de Kai, Kai recibe el aviso con `author_name: "Beto"`.

### Rechaza

```
Ana                   Server                       Workspace
───                   ──────                       ─────────
  │                       │                                │
  │── Resolve ───────────→│                                │
  │   {prop_id, accept=F} │                                │
  │                       │ resolve_use_case:              │
  │                       │   proposals.pop(prop_id)       │
  │                       │   (no toca workspace)          │
  │                       │   contenido_actual = ws[x.py]  │
  │                       │                                │
  │                       │── Update ──→ (SOLO a Beto)
  │                       │   {x.py, contenido_actual}     │
```

Beto recibe el contenido ACTUAL del archivo. El cliente del IDE detecta el contenido distinto del que tiene en pantalla y muestra el revert visual: lo que Beto estaba tipeando desaparece y vuelve a lo que tiene Ana.

## Caso 5: Colisión por línea (sin dueño)

Capa 5. Si dos personas tocan el mismo archivo SIN dueño y ambos están conectados:

```
Ana presente en x.py, línea 10  (modificando una def)
Beto envía Update sobre x.py, tocando líneas 9-12

Server:
  dueño = None
  tocadas = lineas_tocadas(viejo, nuevo) → {9, 10, 11, 12}
  ocupadas_por_otros = roster.lineas_ocupadas(x.py, excepto=beto) → {10}  # Ana
  tocadas & ocupadas → {10}  ≠ ∅
  → rebote

Server → Beto SOLO: Update{x.py, viejo}  (revert visual)
```

Beto ve su cambio deshecho. Ana sigue editando tranquila.

**Regla de prioridad**: la presencia gana. Quien está presente en la línea tiene "ownership transitorio" mientras edita. Beto se ve obligado a esperar / hablar con Ana / pedir ownership explícito (`Claim`).

`lineas_tocadas(viejo, nuevo)` usa LCS truncado (`_LCS_MAX_CELDAS`); si excede, fallback defensivo = "tocó todas las líneas" (rebota más, no menos).

## Caso 6: Tomar ownership explícito

```
Beto                  Server                       Ownership
────                  ──────                       ─────────
  │── Claim ───────────→│                              │
  │   {path: "x.py"}    │                              │
  │                     │ ownership.owner(x.py) → None │
  │                     │ ownership.claim(x.py, beto) →│
  │                     │ ownership_store.guardar()    │
  │                     │                              │
  │←── Ownership ────────────────────→ (a todos)
  │   {owners: {..., x.py: beto}}                       │
```

Si el archivo no tenía dueño: Beto lo reclama. Si ya tenía dueño: `claim` es no-op (devuelve False) — ownership es coordinación, no robo. **El admin del equipo es quien puede reasignar a la fuerza**.

## Caso 7: Reasignación por el admin

```
Líder (admin)            Server                  Ownership
─────────────            ──────                  ─────────
  │                          │                       │
  │── AdminAssign ──────────→│                       │
  │   {path, username: "kai"}│                       │
  │                          │ _es_admin_o_logear() ✓│
  │                          │ teams.es_miembro(team, kai) → True
  │                          │ ownership.asignar(path, kai) →│
  │                          │ ownership_store.guardar() │
  │                          │                       │
  │←──── Ownership ───────────────→ (a todos)
  │   {owners: {..., path: kai}}                     │
```

`asignar` NO respeta al dueño anterior — el admin reparte zonas. La compuerta de admin se valida en el inbound (necesita logging contextual).

Variante: `AdminAssignManyMessage{paths, username}` reparte muchos en una sola operación; el broadcast es uno solo.

`username=""` = revocar (`ownership.liberar(path)`).

`AdminAssignMany` filtra path-a-path con `path_seguro` (M1): un path inseguro en la lista no debe meter ownership fantasma ni anular el resto.

## Caso 8: Borrar archivo

```
Ana (dueña de x.py)   Server                       Workspace + Ownership + Proposals
───                   ──────                       ─────────────────────────────────
  │── Delete ──────────→│                                          │
  │   {path: "x.py"}    │                                          │
  │                     │ ownership.owner(x.py) → "ana" (sos vos)  │
  │                     │── workspace.delete(x.py) ────────────────→│
  │                     │── proposals.drop_path(x.py) ─────────────→│
  │                     │   proposals_store.borrar_path()           │
  │                     │── ownership.liberar(x.py) ───────────────→│
  │                     │   ownership_store.guardar()               │
  │                     │   rt._analizado.pop(x.py)                 │
  │                     │                                          │
  │←── Delete ─────────────────→ (a todos)
  │   {path: "x.py"}                                                │
  │←── Ownership ──────────────→ (a todos)
  │   {owners: {... sin x.py}}                                      │
```

Borrar es del dueño (o de cualquiera si no tiene dueño). Tras el delete: el path puede recrearse, y quien lo recrea pasa a ser dueño nuevo (case 1).

## Topes y rechazos

| Tope | Si rebasa | Mensaje al cliente |
|---|---|---|
| `MAX_BYTES_ARCHIVO` (1MB) | Workspace levanta `WorkspaceLleno` | El update se rechaza con mensaje legible |
| `MAX_ARCHIVOS` (50k) | Idem | Idem |
| `MAX_BYTES_TOTAL` (256MB) | Idem | Idem |
| `MAX_CONTENT_BYTES` propuesta (1MB) | `Proposals.put` levanta `PropuestaInvalida` | Idem |
| `MAX_POR_AUTOR` propuestas (50) | Idem | "demasiadas propuestas pendientes (>50); resolvé o abandoná las viejas" |
| Path inseguro | `DiskStorage._destino` levanta `ValueError` | El update se rechaza en el dispatch (sin tocar memoria) |

Los topes son **blandos por workspace** y configurables vía env. Si un equipo legítimo necesita más, el operador puede subirlos sin recompilar.
