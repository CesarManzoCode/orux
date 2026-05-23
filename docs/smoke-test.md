# Smoke test E2E — pre-anuncio

Guión para ejecutar **en producción** (`https://orux.space`) antes de publicar el lanzamiento. Cubre el viaje real de un usuario nuevo desde que ve un link en X/foro hasta que está editando con un compañero. **Tiempo estimado**: 30–45 min.

> **Preparación**: dos navegadores (o uno normal + uno en incógnito). Anota en una libreta lo que veas raro — al final tenés un checklist para reportar.

---

## Fase 0 · Sanidad de infraestructura (5 min, antes de tocar la UI)

Estos son `curl`s desde tu terminal. Validan que **lo invisible** está OK antes de gastarse el primer signup real.

| # | Comando | Esperado |
|---|---|---|
| 0.1 | `curl -I https://orux.space/` | `200 OK`, `content-type: text/html` |
| 0.2 | `curl -I https://orux.space/og.png` | `200 OK`, `content-type: image/png` |
| 0.3 | `curl https://orux.space/robots.txt` | bloque User-agent + `Sitemap: https://orux.space/sitemap.xml` |
| 0.4 | `curl https://orux.space/sitemap.xml` | XML con `<loc>https://orux.space/</loc>` |
| 0.5 | `curl https://orux.space/api/v1/status` | `{"ok": true, "uptime_s": <int>, "version": "..."}` |
| 0.6 | `curl https://orux.space/api/v1/health` | `{"ok": true, ...}` |
| 0.7 | `curl -X POST https://orux.space/api/v1/track -H 'content-type: application/json' -d '{"event":"smoke","url":"/","referrer":""}'` | `204` (sin cuerpo) |

Si **alguno falla**, parar acá y arreglar antes de tocar la UI.

---

## Fase 1 · Landing y meta (5 min)

Browser principal en **modo incógnito** (para emular un visitante real sin cookies/cache).

1. **Abrir `https://orux.space/`** con DevTools abierto (F12).
   - Tab **Console**: cero errores rojos. Warnings amarillos pueden existir (libs viejas) — anotar pero no bloquea.
   - Tab **Network**: la landing carga en <2s en conexión normal. Filtrar por "Img" para ver `og.png` y por "Fetch/XHR" para ver el POST a `/api/v1/track` (pageview).
2. **Probar el switcher de idioma** ES/EN. Cambia textos, persiste al refresh.
3. **Hacer scroll completo**. Mirar:
   - Hero cinemático corre el loop completo (~12s) sin parpadeos.
   - Pilares, cómo funciona, FAQ, precio. Ningún string raro tipo "undefined" o `[object Object]`.
   - Footer: link a GitHub abre `github.com/CesarManzoCode/laidea` en pestaña nueva, mailto a `hola@orux.space` abre cliente de correo.
4. **Probar share preview** (opcional pero útil):
   - Pegar `https://orux.space` en Twitter compose (sin publicar) → ve preview con og.png + título + descripción.
   - Idem en WhatsApp Web a un grupo de prueba.

**Reportar si**: alguna sección del hero se ve cortada, links muertos, scroll laggy, console errors, mobile layout roto (probá DevTools → Toggle device toolbar → iPhone 14).

---

## Fase 2 · Signup edge cases (10 min)

Browser principal incógnito. Llegamos al login vía botón "Entrar" o tipeando `/app/`.

5. **Password corta** — username válido, password `1234` (< 8). Esperado: error local del cliente "mínimo 8 caracteres" antes de pegarle al server.
6. **Username con char inválido** — `usuario con espacio` o `ana@x` o `usuari@`. Esperado: error claro "usa solo letras, números, '.', '_' o '-'".
7. **Password sin coincidir** (en signup) — `Password` y `Confirm` distintos. Esperado: error local "las contraseñas no coinciden".
8. **Sin aceptar términos** — checkbox vacío al submit. Esperado: botón disabled o error.
9. **Rate limit login** — 4 intentos rápidos con password mala. Esperado: tras el 3º, error "demasiados intentos desde tu red, esperá unos minutos" (ahora **traducido al EN** si estás en EN).
10. **Signup exitoso real** — usuario `smoke-N` (N = epoch corto), password `OruxSmoke12!` o similar, aceptar términos. Esperado: entra al Hub.

**Reportar si**: algún error queda en "Error" genérico sin contexto, el spinner del botón no se apaga después de respuesta, o si después de signup quedás en una pantalla intermedia sin progresar.

---

## Fase 3 · Hub + crear team + invite (5 min)

11. **Empty state del Hub** — primera vista sin teams. Esperado: ver el icono + título "Aún no estás en ningún equipo" + **botón primario "Crear mi primer equipo"** + link "o unirme con un código". Sin esto, hay un bug (sería el viejo flecha decorativa).
12. **Crear team** — clic en "Crear", nombre `smoke-team-1`. Esperado: foco en el input, Enter dispara, entra al IDE.
13. **Edge: nombre con `<script>`** — crear otro team y poner `<script>alert(1)</script>` como nombre. Esperado: error "usa solo letras, números y puntuación normal" antes de enviar.
14. **Edge: nombre vacío / espacios** — debería rechazar.
15. **Crear invite** — desde el IDE, abrir el modal de invitación, generar código. Copiarlo (botón "Copiar"). Esperado: toast "✓ copiado" y el código de un solo uso visible.

**Reportar si**: el invite no se copia al portapapeles, el modal queda colgado, o el error de validación se muestra demasiado tarde (después de un round-trip al server pudiendo haberse validado localmente).

---

## Fase 4 · Tutorial OruxBot (5 min)

El tutorial se dispara automáticamente en la **primera entrada** de un admin a un team virgen. Si ya lo hiciste en otro test, `localStorage.removeItem("orux_tutorial_done")` en la consola y recargar.

16. **Tutorial fluye OK** — clic en cada paso de la narrativa. Pausa entre pasos sin trabarse. Spotlight apunta a elementos visibles.
17. **Escape mid-tutorial** — presionar `Esc`. Esperado: cierra limpio, queda en el IDE.
18. **Reabrir tutorial (opcional)** — `localStorage.removeItem("orux_tutorial_done")` + reload. Probar el botón "Saltar" (top-right).
19. **Edge: pasarse 18 segundos en un paso `click`** — sin clickear. Esperado: aparece el botón "Continuar" en el bot (capa 36, G.1 ya implementado). Si no aparece, hay un bug en el guardrail.

**Reportar si**: el spotlight queda apuntando a un elemento invisible, el bot se queda parado en un paso, o si tras "Empezar" no quedás en el IDE limpio.

---

## Fase 5 · IDE multi-usuario (10 min)

Ahora el segundo browser (incógnito separado, o un browser distinto).

20. **(browser B)** Abrir `orux.space/app/`, registrar `smoke-B-N`, aceptar términos.
21. **(browser B)** En el Hub, clic en "Unirme", pegar el código del paso 15. Esperado: entra al mismo team.
22. **(browser A)** En el IDE, abrir el Inspector (panel derecho) → sección "Presencia". Esperado: ver a `smoke-B-N` listado **en vivo**, con su color.
23. **(browser A)** Crear un archivo `test.py` con contenido `def hola(): return "mundo"`. Aún no Ctrl+S.
24. **(browser B)** Refresh la vista de archivos. Esperado: aparece `test.py` con el mismo contenido.
25. **(browser B)** Clic en `test.py`, ver el archivo de A (no eres dueño aún). Probar editar — los cambios aparecen como **draft local**, NO viajan al server hasta Ctrl+S.
26. **(browser B)** Clic en "reclamar" en el Inspector (sección "ownership"). Esperado: spinner ~1s, después ves "tuyo" en el panel. Si pasan 3s sin confirmar, esperado: toast "No se pudo reclamar...".
27. **(browser A)** Mirar el Inspector. `test.py` ahora muestra "de smoke-B-N".
28. **(browser B)** Editar `test.py`: cambiar la firma a `def hola(nombre):`. Ctrl+S. Esperado: toast "✓ guardado y analizado" o similar.
29. **(browser A)** Esperado en el Inspector → sección "impacto": si A tiene otros archivos que usan `hola`, aparece un aviso. (Si no hay otros archivos, esta sección no aplica.)

**Reportar si**: la presencia no se actualiza en vivo, el ownership no se sincroniza, el draft local no se preserva al hacer scroll, o si Ctrl+S no produce ningún feedback visible.

---

## Fase 6 · Reconexión y persistencia (5 min)

30. **(browser A)** Cerrar el WS a mano: DevTools → Application → Service Workers (si hay) → Unregister. O bien: subir/bajar el WiFi por 5s.
    - Esperado: el badge de conexión en TopBar/StatusBar va a `desconectado → conectando → conectado` en ~5s. **El usuario NO necesita refrescar**.
31. **(browser A)** Refresh completo de la página (F5). Esperado: **auto-login** vía el token en `localStorage`. Vuelve al mismo team, mismo archivo abierto. Cero re-login manual.
32. **(browser A)** Logout completo desde el menú. Esperado: vuelta al `/login` limpio.
33. **(browser A)** Login con `smoke-N` y la password de arriba. Esperado: entra al Hub con `smoke-team-1` listado.

**Reportar si**: el auto-login pide credenciales (debería ser invisible), el logout deja restos en localStorage, o si tras reconnect el editor muestra estado obsoleto.

---

## Fase 7 · Variantes opcionales

Hacer SI hay tiempo:

34. **OAuth GitHub** — desde `/login`, clic en "Continuar con GitHub". Esperado: redirige a GitHub, autorizar, vuelve a Orux logueado como `gh:<tu-login>`. Si está desactivado en este deploy, ese botón no aparece.
35. **Push a un repo real** — desde la vista Git del IDE, hacer `commit` + `push`. Esperado: el push usa credenciales efímeras, devuelve URL de PR de GitHub.
36. **Stripe checkout (test mode)** — desde el Hub, clic en "Mejorar a Premium" en un team free. Esperado: redirige a Stripe checkout. Cancelar → volver al Hub con toast "pago cancelado". (Solo si Stripe está configurado en este deploy.)

---

## Fase 8 · Cross-browser (10–15 min)

Las Fases 1–7 las hacés en Chrome. Esta fase replica las **partes críticas** en otros motores. La marca técnica es: si la landing y el primer signup funcionan en Safari + Firefox + un mobile, **el resto** muy probablemente también — esos son los motores con quirks distintos a Chrome.

> Si no tenés acceso a alguno de los navegadores, saltá ese sub-bloque. Sumar **al menos** Safari macOS o iOS, y un Firefox cualquiera.

### 8.1 · Safari macOS (5 min)

Safari (WebKit) es el motor con más diferencias respecto a Chrome. Es donde más bugs aparecen sin darse cuenta porque la mayoría desarrollamos en Chrome.

- **Landing** (`orux.space/`):
  - Hero cinemático corre suave (sin saltos, sin "frame skipping"). Si lo ves trabado, anotalo.
  - Los gradientes / sombras se ven idénticos a Chrome (Safari renderiza algunos blends distinto).
  - Switcher ES/EN funciona y persiste tras refresh.
  - Scroll vertical sin layout shift.
- **Signup** (`orux.space/app/`):
  - Form de signup acepta input.
  - Tras crear cuenta, entra al Hub.
  - Crear team, entrar al IDE.
- **WebSocket**:
  - Estado de conexión llega a `conectado` (badge en TopBar).
  - El editor abre. Tipear y abrir DevTools (Cmd+Opt+I) → Network → WS → ver mensajes en vivo.

**Bugs típicos de Safari que vale buscar**:
- Inputs cuyo placeholder no se ve hasta el segundo click.
- `position: sticky` que rompe (la nav top del landing usa sticky).
- Fechas/tiempos parseados como `NaN` (más relevante si hay "hace 3m" en presencia).
- WebSocket que NO reconecta después de pausa de la pestaña (Safari es agresivo cerrando conexiones en background).

### 8.2 · Safari iOS (mobile) (5 min)

Si tenés iPhone o el simulador en macOS (Xcode):

- **Landing**:
  - El hero se ve completo sin scroll horizontal accidental.
  - Tamaños de fuente legibles sin zoom manual.
  - Los chips de "EN VIVO" / footer no se cortan a la derecha.
  - Tap en CTAs responde (no hay "doble tap" requerido por culpa de touch-action).
- **Login/Signup**:
  - El input no se acerca raro al focus (viewport bien configurado).
  - Teclado iOS no oculta el botón de submit.
- **IDE** (opcional, no es target de uso real):
  - Anotar si el editor es usable. NO es bug si NO lo es — el IDE es desktop-first.

**Bugs típicos en mobile Safari**:
- 100vh incluye la barra del navegador → contenido se corta.
- Inputs hacen zoom al focus (si el font-size es <16px).
- `<input type="password">` con autocompletado raro de iCloud Keychain.

### 8.3 · Firefox (3 min)

- **Landing** completa sin errores en console (`Ctrl+Shift+K`).
- **Signup + entrar a un team**:
- **Editor**: tipear, hacer Ctrl+S, ver el toast.

**Bugs típicos de Firefox**:
- CSS `:has()` no soportado en versiones < 121 (poco probable hoy, pero anotar si la sidebar se ve rara).
- WebSocket warnings de tipo "self-signed cert" si Caddy está en localhost (no aplica en orux.space — debería ser limpio).

### 8.4 · Chrome Android (mobile) (2 min)

Si tenés Android o emulador:

- **Landing**: idem 8.2 pero motor Blink. Si Safari iOS pasa pero Chrome Android no, hay un bug Android-specific (raro).

---

## Reportar hallazgos

Para cada cosa rara que veas, anotar:

```
Fase: <numero>.<sub>
Esperado: <lo que el guión decía>
Visto:    <lo que pasó>
Reproducible: sí / a veces / no sé
Console: <copy/paste de los errors rojos si hay>
Browser: <Chrome 130 / Firefox / Safari / Mobile>
```

Y mandarme la lista. Lo arreglo en orden de severidad:
- 🔴 **Bloqueante**: el usuario no puede progresar (signup roto, IDE no carga).
- 🟡 **Espina**: el usuario progresa pero ve algo raro (mensaje confuso, layout torcido).
- 🟢 **Cosmético**: detalle visual, podría esperar al post-anuncio.

---

## Resultado posible y siguientes pasos

- **Cero hallazgos**: estamos listos para promocionar.
- **Solo 🟢 cosméticos**: estamos listos, los arreglamos durante la primera semana.
- **🟡 espinas**: depende cuántas — si son 1-2 las arreglamos antes; si son 5+ vale la pena un día más de polish.
- **🔴 bloqueante**: parar promo, fix inmediato.
