import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Landing (capa 23b, rehecha): proyecto React PROPIO, pesado y animado, a
// propósito desacoplado del cliente del IDE (no infla su bundle, deploy
// independiente). Sirve en la raíz del dominio: `base: "/"`. El IDE vive
// en /app (su propio build, base /app/). Dockerfile.web compila ambos.
export default defineConfig({
  plugins: [react()],
  base: "/",
  server: { port: 5174 },
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
});
