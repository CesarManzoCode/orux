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
$V/components/prism-ruby.min.js,\
$V/components/prism-c.min.js,\
$V/components/prism-cpp.min.js,\
$V/components/prism-csharp.min.js,\
$V/components/prism-php.min.js,\
$V/components/prism-kotlin.min.js,\
$V/components/prism-swift.min.js,\
$V/components/prism-typescript.min.js,\
$V/components/prism-jsx.min.js,\
$V/components/prism-tsx.min.js,\
$V/components/prism-markdown.min.js"

# Verificá que bajó algo razonable y que typescript quedó adentro:
head -c 80 web/vendor/prism.js ; echo
grep -c 'languages.typescript' web/vendor/prism.js   # debe ser >= 1

git add -f web/vendor/prism.js
git commit -m "vendor: prism.js 1.29.0 (bundle completo, con js/ts)"
```

NO se baja el theme de Prism a propósito: los colores los pone el CSS de
`index.html` sobre las clases `.token.*`, así la métrica del editor
(line-height/padding, contrato con la capa de presencia) no se toca. Aunque
el bundle estuviera mal, el cliente ahora degrada a texto plano (try/catch)
en vez de romperse — pero con este bundle correcto, TS resalta de verdad.

Para servirlo no hace falta rebuild: `web/` es bind-mount de Caddy. Tras el
`git add`/commit, en cualquier máquina basta `git pull` y hard-refresh.
