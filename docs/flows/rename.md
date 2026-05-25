# Flow: Rename (detección + propagación)

Capa 26. Cuando un dev renombra un símbolo (clase, función, atributo) en su archivo, el sistema lo detecta y actúa de dos formas distintas según el plan.

## Qué cuenta como rename

`detectar_rename(viejo_simbolos, nuevo_simbolos) -> Rename | None`

**Exactamente** estos criterios DEBEN cumplirse:

1. **1 quitado y 1 agregado** en la misma clase.
2. **Mismas firmas** (mismos parámetros, mismo tipo de retorno).
3. **`__init__` guardia** (Python): si el `__init__` cambió, los cambios deben ser CONSISTENTES con el rename (capa 26b).

Si NO cumple → NO es rename detectable → impacto normal con aviso genérico.

**Caso real del usuario** (capa 26b): rename mezclado (2 quitados + 1 agregado) NO califica como rename → sigue sin codemod a propósito. El dev hace los renames manuales o aprueba paso a paso.

### Capa 26b: rename de atributos

Antes solo se detectaban renames de métodos. La capa 26b agregó **atributos de instancia** (`self.X = Y` del `__init__`):

```python
# viejo
class Usuario:
    def __init__(self, id_):
        self.id = id_
        self.nombre = ""

# nuevo
class Usuario:
    def __init__(self, id_):
        self.identifier = id_   # ← rename
        self.nombre = ""
```

`detectar_rename` ve un atributo quitado (`id`) y uno agregado (`identifier`) en `__init__`. La guardia del `__init__` se relaja porque los cambios SON consistentes con el rename detectado.

## Free: aviso accionable

Cuando se detecta rename pero el plan no aplica codemod:

```python
if rename is not None and rename.clase in razones:
    razones = {**razones, rename.clase: texto_sugerencia(rename)}
```

El motivo genérico se reemplaza:

```
"se renombró firma"   →   "se renombró Usuario.get_id → obtener_id; actualizá los usos"
```

El aviso (a quién, byte-idéntico) sigue saliendo igual. Solo cambia el TEXTO del motivo para ese símbolo en particular. El dev abre `auth.py`, busca `Usuario.get_id`, lo reemplaza por `obtener_id` manualmente.

## Premium: propaga como propuestas (capa 26)

`calcular_propagar_rename` orquesta:

```
Ana cambia Usuario en x.py: renombra get_id → obtener_id
                  │
                  ↓
Save (Ctrl+S) → detectar_rename → Rename{clase: "Usuario", viejo: "get_id", nuevo: "obtener_id"}
                  │
                  ↓
propagar_rename:
  snap = rt.workspace.snapshot()
  plan = "premium"
  
  afectados = impacto(snap, x.py, base, actual, sesion)
  # → {"Usuario": ["auth.py", "ventas.py", "tests/test_user.py"]}
  
  for af in afectados.get("Usuario", []):
    contenido = snap[af]
    propuesto = aplicar_rename(contenido, "get_id", "obtener_id")
    if propuesto == contenido:
      continue  # el texto no aparece
    
    dueño = rt.ownership.owner(af)
    if dueño is None or dueño == ana:
      # aplicar directo
      rt.workspace.update(af, propuesto)
      rt._analizado[af] = propuesto  # avanzar baseline (no re-avisar)
      → broadcast Update{af, propuesto}
    else:
      # propuesta para el dueño
      prop = rt.proposals.put(
        path=af,
        author_id=ana,
        author_name="OruxBot · rename Usuario.get_id→obtener_id",
        content=propuesto,
      )
      → Proposal al dueño
```

## Lo que ve cada actor

### Ana (autora del rename)

Termina su `Ctrl+S`. Si el rename impacta:

- Archivos sin dueño o suyos: ya están actualizados en su pantalla (broadcast Update).
- Archivos ajenos: NO ve nada. La propuesta vive en el dueño hasta que apruebe/rechace.

### Kai (dueño de `auth.py`)

Recibe `ProposalMessage` con:

```python
Proposal{
    id: "auth.py::ana",
    path: "auth.py",
    author_id: "ana",
    author_name: "OruxBot · rename Usuario.get_id→obtener_id",
    content: <auth.py con el rename aplicado>,
}
```

El IDE muestra la ventana de aprobar/rechazar de capa 4 — la MISMA UI que ya conoce, con la etiqueta `"OruxBot · rename Usuario.get_id→obtener_id"` arriba (en vez de "Ana" plano).

Kai ve el diff de `auth.py`: solo cambia `get_id` → `obtener_id` en los usos. Aprueba → el archivo se actualiza en su workspace y en el de todos. Rechaza → el codemod se descarta.

**Decisión load-bearing**: la aprobación es la red de seguridad que hace seguro un codemod heurístico. Si `aplicar_rename` tiene un edge case (string que contiene `"get_id"`, comentario, etc.), Kai lo ve y rechaza. El dueño es el último filtro.

## El codemod (`aplicar_rename`)

```python
def aplicar_rename(contenido: str, viejo: str, nuevo: str) -> str:
    """Reemplaza viejo→nuevo con word-boundary, no en strings/comentarios.
    
    Si viejo o nuevo están vacíos: devuelve contenido sin tocar
    (BACKEND-AUDIT-0231: viejo='' convertía el patrón en \\.\\b
    que pisaba cada punto).
    """
```

Heurístico:

- Word-boundary estricto: `getter` no matchea cuando `viejo="get"`.
- Detecta strings y comentarios (lenguaje-aware en Python; tree-sitter en otros).
- No reemplaza en attribute access cruzado (`obj.get_id` matchea, `obj.get_id_secundario` no).

Es heurístico — no resuelve casos como acceso reflexivo (`getattr(obj, "get_id")`). Para esos, el dueño aprueba viendo el diff y, si nota algo, rechaza.

## Por qué premium

El codemod automático ahorra trabajo manual real (renames atraviesan 5-20 archivos en un proyecto medio). Aplicarlo automáticamente Y mostrar el diff es la combinación que:

1. Hace el cambio masivo trivial (cero "find & replace" del dev).
2. Mantiene la red de seguridad de capa 4 (el dueño aprueba).
3. NO inventa UI nueva (la propuesta es la pieza que ya existía).

Free recibe el aviso accionable; premium recibe el cambio listo para aprobar. Ambos terminan con el mismo resultado, pero premium ahorra ~5 min por rename medio.

## Por qué la etiqueta `"OruxBot · ..."`

El cambio lo construye el server (codemod), no lo tipeó nadie. Mostrar `author_name: "Ana"` plano sería engañoso — Ana no editó ese archivo.

`OruxBot · rename X→Y` deja claro:

- Es el sistema proponiendo.
- El contexto del rename (qué se renombró).
- El autor real (`author_id: "ana"`) sigue siendo Ana para el flujo (si Kai rechaza, el revert va a Ana).

## Tests

`backend/tests/test_rename.py`:

- `detectar_rename`: casos básicos, mismas firmas, atributos (capa 26b), rechazos (firmas distintas, múltiples cambios, etc.).
- `aplicar_rename`: word-boundary, comentarios, strings, guards de viejo/nuevo vacíos.
- `texto_sugerencia`: formato accionable.

`test_sync.py::test_rename_propaga_*`: integración con el flujo Save → propagar_rename → propuestas/updates.

## Diagnóstico

| Síntoma | Causa probable |
|---|---|
| Rename no detectado | NO cumple las 3 reglas (1+1 con mismas firmas, __init__ consistente). Cambio mezclado intencional. |
| Premium pero solo recibió aviso | Caller no llamó a `propagar_rename` (verificar `_h_save:plan != premium`). |
| Codemod aplicado pero archivo intocable | `aplicar_rename` devolvió `propuesto == contenido` (texto no aparece). Probablemente el caller no usa el símbolo directo. |
| Etiqueta no es "OruxBot" | Bug del frontend: chequear `Proposal.author_name` en `ProposalMessage`. |

Ver [`domain/analysis.md`](../domain/analysis.md) sección Rename.
