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

```bash
cd ~/laidea
curl -fsSL -o web/vendor/prism.js \
'https://cdn.jsdelivr.net/combine/npm/prismjs@1.29.0/prism.min.js,npm/prismjs@1.29.0/components/prism-python.min.js,npm/prismjs@1.29.0/components/prism-json.min.js,npm/prismjs@1.29.0/components/prism-bash.min.js,npm/prismjs@1.29.0/components/prism-yaml.min.js,npm/prismjs@1.29.0/components/prism-sql.min.js,npm/prismjs@1.29.0/components/prism-java.min.js,npm/prismjs@1.29.0/components/prism-go.min.js,npm/prismjs@1.29.0/components/prism-rust.min.js,npm/prismjs@1.29.0/components/prism-ruby.min.js,npm/prismjs@1.29.0/components/prism-c.min.js,npm/prismjs@1.29.0/components/prism-cpp.min.js,npm/prismjs@1.29.0/components/prism-csharp.min.js,npm/prismjs@1.29.0/components/prism-php.min.js,npm/prismjs@1.29.0/components/prism-kotlin.min.js,npm/prismjs@1.29.0/components/prism-swift.min.js,npm/prismjs@1.29.0/components/prism-typescript.min.js,npm/prismjs@1.29.0/components/prism-jsx.min.js,npm/prismjs@1.29.0/components/prism-tsx.min.js,npm/prismjs@1.29.0/components/prism-markdown.min.js'

# Verificá que bajó algo razonable (no un error de jsDelivr):
head -c 80 web/vendor/prism.js ; echo

# Versionalo para que sea reproducible (no se pierde al re-clonar):
git add -f web/vendor/prism.js
git commit -m "vendor: prism.js 1.29.0 (resaltado multilenguaje)"
```

`prism.min.js` (core) ya trae markup, css, clike y javascript; el resto se
suma como componentes en orden seguro (typescript/jsx/tsx después de
javascript). NO se baja el theme de Prism a propósito: los colores los pone
el CSS de `index.html` sobre las clases `.token.*`, así la métrica del editor
(line-height/padding, contrato con la capa de presencia) no se toca.

Para servirlo no hace falta rebuild: `web/` es bind-mount de Caddy. Tras el
`git add`/commit, en cualquier máquina basta `git pull` y hard-refresh.
