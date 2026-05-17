import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build estático plano: sale a `dist/`, lo sirve Caddy. Capa 23b: la app
// se movió de `/` a `/app` (el root ahora es la landing estática). `base:
// "/app/"` => los assets se referencian como `/app/assets/...` absolutos
// y el dist se copia a `/srv/app/` (ver Dockerfile.web/Caddyfile). No hay
// router en el cliente, así que no hay rutas que rebasar; el WS se deriva
// del origen (path-independiente), no se ve afectado.
export default defineConfig({
  plugins: [react()],
  base: "/app/",
  server: { port: 5173 },
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
});
