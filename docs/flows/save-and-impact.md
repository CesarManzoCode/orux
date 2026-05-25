# Flow: Save (Ctrl+S) y análisis de impacto

Cuando un dev hace **Ctrl+S** sobre un archivo, no se guarda nada (el contenido ya está sincronizado por los Updates por tecla). Lo que pasa es algo más interesante: **se dispara el análisis semántico** y el sistema avisa al dueño de cada archivo afectado.

Esto es la capa 6/19/24/26 — el diferencial del producto.

## Por qué Ctrl+S y no por tecla

El análisis costaba ~50-500ms por archivo. Si lo corriéramos por tecla, satúrabamos el server (cada Update = un análisis). Solución (capa 19): el análisis corre en el **checkpoint** explícito del dev.

Beneficios:

- Modelo mental claro: "salvé" = "decí ahora si rompí algo".
- Permite al dev hacer 10 tipeos seguidos sin avalancha de avisos parciales.
- Cero overhead durante el flow real (Update sigue siendo trivial).

## Baseline del checkpoint

Cada archivo tiene un **baseline**: el contenido en el último Save (o el contenido al primer Update si nunca se hizo Save).

```python
# en runtime.py:
self._analizado: dict[path, str] = {}
```

Cuando Ana hace el primer Update sobre `x.py`:

```python
# update_use_case:
rt._analizado.setdefault(cmd.path, viejo)
```

`viejo` es el contenido PREVIO a editar (vacío si es nuevo, lo cargado si existente). Se siembra una vez.

Cuando Ana hace Ctrl+S:

```python
# _h_save:
actual = rt.workspace.snapshot().get(message.path)
base = rt._analizado.get(message.path, "")
rt._analizado[message.path] = actual   # baseline avanza SIEMPRE
```

Diff = `base → actual`. El baseline avanza haya o no impacto: el próximo Ctrl+S mide desde acá.

## Flujo completo

```
Ana                  Server WS               application/impacto    AnalysisPort   teams         Roster (otros)
───                  ─────────               ───────────────────    ────────────   ─────         ──────────────
  │                      │                            │                  │             │              │
  │── Save{x.py} ───────→│                            │                  │             │              │
  │                      │ actual = ws.snapshot()[x.py]                  │             │              │
  │                      │ base = rt._analizado[x.py]                    │             │              │
  │                      │ rt._analizado[x.py] = actual                  │             │              │
  │                      │                            │                  │             │              │
  │                      │ (a hilo: detectar_rename)  │                  │             │              │
  │                      │                            │                  │             │              │
  │                      │ ren? = await to_thread(rename._det)           │             │              │
  │                      │                            │                  │             │              │
  │                      │ plan = await teams.plan(team_id) ─────────────────────────────→│              │
  │                      │ ←── "free" ──────────────────────────────────────────────────│              │
  │                      │                            │                  │             │              │
  │                      │ si rename Y permite_rename(plan):              │             │              │
  │                      │   propagar_rename(...)  (capa 26 premium)     │             │              │
  │                      │ si no:                                         │             │              │
  │                      │   notificar_impacto(rt, x.py, base, actual, ana_id, "Ana", rename=ren?) │
  │                      │                            │                  │             │              │
  │                      │── calcular_impacto_save() →│                  │             │              │
  │                      │                            │                  │             │              │
  │                      │                            │ plan = await teams.plan() ─────────→│              │
  │                      │                            │ cap_langs = limites(plan)         │              │
  │                      │                            │                  │             │              │
  │                      │                            │── to_thread: ────→│             │              │
  │                      │                            │   sesion = rt.lsp_sesion(py, cap_langs)        │
  │                      │                            │   af = impacto(snap, x.py, base, actual, sesion)
  │                      │                            │   raz = motivos(...)                            │
  │                      │                            │   chip = analizador_efectivo(x.py, sesion)     │
  │                      │                            │←──── {af, raz, chip}                          │
  │                      │                            │                  │             │              │
  │                      │                            │ por_archivo = reagrupar(af)                    │
  │                      │                            │ for af, syms in por_archivo:                   │
  │                      │                            │   dueño = rt.ownership.owner(af)                │
  │                      │                            │   if dueño:                                    │
  │                      │                            │     ImpactoEfectos.mensajes_directos.append(   │
  │                      │                            │        (dueño, ImpactMessage(...)))            │
  │                      │                            │                                                │
  │                      │                            │ (si plan premium: onda transitiva, otra hilo)  │
  │                      │                            │                                                │
  │                      │←── ImpactoEfectos ─────────│                  │             │              │
  │                      │                                                              │              │
  │                      │ for dueño, msg in efectos.mensajes_directos:                 │              │
  │                      │   await server._enviar_a(rt, dueño, encode(msg))             │              │
  │                      │                                                              │              │
  │                      │── Impact ──────────────────────────────────────────────────────→ Kai (dueño de auth.py)
  │                      │   {source: x.py, affected: auth.py,                          │              │
  │                      │    symbols: ["Usuario"], motivos: ["se renombró firma"],    │              │
  │                      │    severidades: ["alta"], analizador: "ast"}                  │              │
```

## Lo que el dueño recibe

```
ImpactMessage{
    source_path: "x.py",            # archivo que cambió
    author_name: "Ana",             # quien hizo el cambio
    affected_path: "auth.py",       # tu archivo
    symbols: ["Usuario"],           # qué símbolo cambió
    motivos: ["se renombró firma"], # por qué importa
    severidades: ["alta"],          # alta | media | baja
    cadena?: [...],                 # solo en transitivo
    analizador?: "ast"              # chip: "lsp"/"ast"/"treesitter"/"regex"
}
```

El cliente del IDE lo muestra en el Inspector lateral. Con severidad alta + autor = alguien activo + path = archivo que tenés abierto → es accionable. El UI no te bloquea — te informa.

## Caso premium: impacto transitivo

Premium agrega una segunda tanda: la onda por **interfaz contaminada**.

```
1. Ana cambia Usuario en x.py
2. y.py importa Usuario, y define class UserService que tiene .crear_usuario(u: Usuario) → ...
3. z.py importa UserService y la usa
4. Sin transitivo: solo se avisa a y.py
5. Con transitivo: también se avisa a z.py
   "cadena": ["x.py:Usuario", "y.py:UserService"]
```

**Decisión clave** (capa 24): NO es "referencias de referencias" (eso explota). Es propagación **solo por interfaz contaminada**:

- Si `Usuario` aparece en la INTERFAZ de `UserService` (en `crear_usuario`, en `__init__`, en superficie) → la interfaz de `UserService` quedó contaminada → se avisa Y se propaga.
- Si `Usuario` aparece SOLO en el CUERPO de `UserService` (en una variable local de un método) → la interfaz NO cambió → se avisa TERMINAL y la onda CORTA.

Esto acota la explosión combinatoria. `impacto_transitivo` BFS con `max_prof=4`, `max_nodos=200`, ciclos por `visitados`. Si trunca, lo dice honesto (`truncado=True` → sufijo "análisis truncado (cambio muy amplio)").

## Caso rename: detección + propuestas

`detectar_rename(viejo_simbolos, nuevo_simbolos) -> Rename | None`:

Detecta SOLO renames confiables: exactamente 1 quitado + 1 agregado, mismas firmas, en la misma clase. Más complicado que eso (2 quitados + 1 agregado, firmas distintas) → no es rename, es cambio normal.

### Free: aviso accionable

```python
texto_sugerencia(ren)  # "se renombró Usuario.get_id → obtener_id; actualizá los usos"
```

El motivo genérico ("se renombró firma") se reemplaza por este texto en `ImpactMessage.motivos` para el símbolo renombrado. El usuario hace el rename manual con el aviso claro.

### Premium: propaga como propuestas (capa 26)

```python
calcular_propagar_rename(rt, teams, proposals_store, x.py, base, actual, ren, ana_id, "Ana")
```

Para cada archivo afectado donde se usa la clase renombrada:

- `propuesto = aplicar_rename(contenido, ren.viejo, ren.nuevo)` — codemod heurístico.
- Si propuesto == contenido (texto no aparece) → skip.
- **Si sin dueño o propio de Ana**: aplica el update directo. `rt.workspace.update(af, propuesto)`. Avanza baseline (`rt._analizado[af] = propuesto`) para no re-avisar.
- **Si dueño ajeno**: crea propuesta con `author_name = "OruxBot · rename Usuario.get_id→obtener_id"`. El dueño ve la MISMA ventana aprobar/rechazar de capa 4 (sin UI nueva).

El dueño revisa el diff y aprueba. La aprobación = ya pasó por sus ojos. **El codemod heurístico es seguro porque la aprobación es la red de seguridad** — la tesis del producto trabajando a favor.

## El chip del analizador (capa 35)

`tiers.analizador_efectivo(path, sesion)` devuelve qué se usó EFECTIVAMENTE:

- `"lsp"`: tier 0 (pyright/tsserver/gopls/rust-analyzer) — fan-out real.
- `"ast"`: tier 1 (Python stdlib `ast`).
- `"treesitter"`: tier 2.
- `"regex"`: tier 3 fallback.

El chip se calcula CON la sesión LSP que se intentó usar — si la sesión estaba caída, dice `"ast"` no `"lsp"`. Etiquetar afuera (recalculando) se desincronizaría con el resultado real.

El transitivo NO usa LSP a propósito (costo de cómputo) → siempre muestra chip ≠ `"lsp"`.

El cliente del IDE muestra el chip como `.inimp-analiz` cuando NO es `"lsp"`: el dev sabe que el análisis es "best-effort" sin resolución real.

## Por qué async + hilo

El análisis está en un hilo (`asyncio.to_thread`) porque:

- **Parser AST**: aceptable en el loop pero acumula con archivos grandes.
- **tree-sitter**: parser C bloqueante.
- **LSP**: subprocess + spawn (lazy) + IPC bloqueante.

Sin hilo, durante el análisis se freezeaba la presencia/locks/broadcasts de TODO el equipo. Con hilo (capa 16): el análisis NO toca el event loop. Otros mensajes (cursor, claim, etc.) siguen fluyendo.

`snapshot()` antes de la `to_thread` es copia → todo el resto que viaja al hilo son strings inmutables. Thread-safe sin lock.

## Topes del análisis

- **Cap de lenguajes LSP por plan** (capa 22): free=2, premium=INF. Si el equipo ya tiene 2 lenguajes con sesión viva y aparece un 3º, el server NO arranca LSP para ese 3º → degrada a tree-sitter/AST. No rompe, solo es menos preciso.
- **Análisis truncado** (transitivo): `max_prof=4`, `max_nodos=200`. Si trunca, lo dice.

## Diagnóstico

| Síntoma | Causa probable |
|---|---|
| Ctrl+S no genera avisos | El cambio no afecta interfaz pública (cambió cuerpo, no firma) → `cambios_que_importan` devuelve `{}` |
| Chip `"ast"` cuando debería ser `"lsp"` | LSP en cooldown (chequear logs `LSP py arranque #X falló`); o cap del plan saturado |
| Truncado | Cambio muy amplio (modificaste 50 símbolos a la vez). Honesto: el análisis no cuelga, te dice que se truncó |
| `ImpactMessage` sin recibir | Sin dueño en el archivo afectado, o `tiers.lenguaje_de(path) is None` (lenguaje no soportado) |
| Análisis lento | LSP tardando: ver logs `LSP py NO disponible` o sesión muerta auto-recuperándose |

Ver [`domain/analysis.md`](../domain/analysis.md) y [`adapters/lsp.md`](../adapters/lsp.md) para profundidad.
