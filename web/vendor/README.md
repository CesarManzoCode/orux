# web/vendor/

Dependencias de cliente vendorizadas (sin build, sin npm). Las sirve Caddy
igual que el resto de `web/`.

## prism.js (capa 11 — resaltado multilenguaje)

Falta `web/vendor/prism.js` (no se versiona vacío a propósito: lo bajás vos).
Mientras no esté, el cliente cae solo al resaltador vanilla de Python — no
se rompe nada.

Bajalo **en el VPS** (tiene internet; este sandbox no) con jsDelivr, que
combina core + lenguajes en UN archivo, en orden de dependencias correcto.
Pineado a Prism 1.29.0:

**IMPORTANTE (bug que ya pasó):** `prism.min.js` (core de npm) **NO** trae
los lenguajes — ni siquiera `markup/css/clike/javascript`. Hay que sumarlos
explícitamente y EN ORDEN de dependencias: `clike` antes que `javascript`,
`javascript` antes que `typescript/jsx`, `jsx`+`typescript` antes que `tsx`.
Si falta `javascript`, la gramática de `typescript` queda rota y rompía el
editor con archivos `.ts`. El URL de abajo ya está en el orden correcto.
Pineado a Prism 1.29.0:

```bash
cd ~/laidea
P='https://cdn.jsdelivr.net/combine'
V='npm/prismjs@1.29.0'
# SOLO el stack que se usa (regla del proyecto: lo que se usa, no lo que
# existe). NADA de php/ruby/csharp/swift: php depende de `markup-templating`
# y registra un hook GLOBAL que corre en cada Prism.highlight — sin
# markup-templating, ROMPE el resaltado de TODOS los lenguajes (bug visto).
# Si algún día se agrega un lenguaje "templating" (php, ejs, handlebars,
# erb) hay que sumar TAMBIÉN `prism-markup-templating.min.js` antes que él.
curl -fsSL -o web/vendor/prism.js \
"$P/$V/prism.min.js,\
$V/components/prism-markup.min.js,\
$V/components/prism-css.min.js,\
$V/components/prism-clike.min.js,\
$V/components/prism-javascript.min.js,\
$V/components/prism-python.min.js,\
$V/components/prism-json.min.js,\
$V/components/prism-bash.min.js,\
$V/components/prism-yaml.min.js,\
$V/components/prism-sql.min.js,\
$V/components/prism-java.min.js,\
$V/components/prism-go.min.js,\
$V/components/prism-rust.min.js,\
$V/components/prism-c.min.js,\
$V/components/prism-cpp.min.js,\
$V/components/prism-kotlin.min.js,\
$V/components/prism-typescript.min.js,\
$V/components/prism-jsx.min.js,\
$V/components/prism-tsx.min.js,\
$V/components/prism-markdown.min.js,\
$V/components/prism-docker.min.js,\
$V/components/prism-makefile.min.js"

# VERIFICACIÓN OBLIGATORIA — dos partes:
# 1) los componentes base/stack están (todos >= 1):
head -c 80 web/vendor/prism.js ; echo
for L in clike markup css javascript typescript java cpp go kotlin rust docker; do \
  printf '%s=%s ' "$L" "$(grep -c "languages.$L" web/vendor/prism.js)"; done; echo
# 2) PRUEBA REAL en el navegador (consola, sobre studymation.online):
#    try { Prism.highlight('class A{}', Prism.languages.java,'java') ; console.log('OK') }
#    catch(e){ console.log('ROTO:', e.message) }
#    Tiene que decir OK. "ROTO: ... tokenizePlaceholders" = metiste un
#    lenguaje templating (php/etc.) sin markup-templating.

git add -f web/vendor/prism.js
git commit -m "vendor: prism.js 1.29.0 (stack completo: ts/js/py/java/cpp/go/kotlin/rust/docker/md/...)"
```

NO se baja el theme de Prism a propósito: los colores los pone el CSS de
`index.html` sobre las clases `.token.*`, así la métrica del editor
(line-height/padding, contrato con la capa de presencia) no se toca. Aunque
el bundle estuviera mal, el cliente ahora degrada a texto plano (try/catch)
en vez de romperse — pero con este bundle correcto, TS resalta de verdad.

Para servirlo no hace falta rebuild: `web/` es bind-mount de Caddy. Tras el
`git add`/commit, en cualquier máquina basta `git pull` y hard-refresh.
