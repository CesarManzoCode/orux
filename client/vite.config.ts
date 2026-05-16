import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Build estático plano: sale a `dist/`, lo sirve Caddy igual que antes
// servía web/. Sin animaciones ni magia: una SPA seria. `base: "./"` para
// que funcione servida desde la raíz del dominio sin suposiciones.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: { port: 5173 },
  build: { outDir: "dist", emptyOutDir: true, sourcemap: false },
});
