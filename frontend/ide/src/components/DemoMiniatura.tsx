// Mini-demo embebida en el empty-state del workspace. Un fragmento de
// código simulado con cuatro overlays animados en loop (~10s) que enseñan
// los diferenciadores reales: presencia, impacto semántico, ownership y
// propuestas. La idea es que un equipo recién creado vea — en segundos —
// qué va a pasar cuando haya código, sin que esto le robe el foco a los
// step buttons tutoriales (clonar / crear / invitar): por eso el contenedor
// es neutro (sin fondo verde) y los overlays son chicos.
//
// Decisiones:
// - La animación es CSS pura (keyframes con delays escalonados); no hay
//   estado en React. El navegador la maneja, sin rerenders.
// - Pausable en hover (animation-play-state: paused) por si alguien quiere
//   leer un overlay puntual.
// - Respeta prefers-reduced-motion: los cuatro overlays quedan visibles
//   estáticos al mismo tiempo, en esquinas separadas para no chocar.
// - Los colores de los overlays no son todos verdes: cada uno usa su
//   semántica (verde = presencia viva; ámbar = impacto/aviso; cian =
//   propuesta/info; texto neutro = ownership). Esto mantiene la regla
//   "verde sólo para estado vivo de verdad" y de paso da variedad visual
//   para que la demo se lea como "señales distintas" y no compita con el
//   bloque uniforme verde de los CTAs.
import { useI18n } from "../i18n";

export function DemoMiniatura() {
  const { t } = useI18n();
  return (
    <div className="ews-demo" role="img" aria-label={t.ews_demo_aria}>
      <span className="ews-demo-tag">{t.ews_demo_tag}</span>

      <pre className="ews-demo-code" aria-hidden="true">
        <span className="ews-demo-ln">
          <span className="ews-demo-n">12</span>
          <span><span className="dm-kw">def</span> <span className="dm-fn">procesar_pago</span>(monto, moneda):</span>
        </span>
        <span className="ews-demo-ln">
          <span className="ews-demo-n">13</span>
          <span>    <span className="dm-kw">if</span> monto &lt;= <span className="dm-num">0</span>:</span>
        </span>
        <span className="ews-demo-ln">
          <span className="ews-demo-n">14</span>
          <span>        <span className="dm-kw">return</span> <span className="dm-kw">None</span></span>
        </span>
        <span className="ews-demo-ln">
          <span className="ews-demo-n">15</span>
          <span>    pago = <span className="dm-cls">Pago</span>(monto, moneda)</span>
        </span>
        <span className="ews-demo-ln">
          <span className="ews-demo-n">16</span>
          <span>    <span className="dm-kw">return</span> pago.<span className="dm-fn">cobrar</span>()</span>
        </span>
      </pre>

      <span className="ews-demo-ev ews-demo-pres" aria-hidden="true">
        <span className="ews-demo-dot" />
        {t.ews_demo_pres}
      </span>
      <span className="ews-demo-ev ews-demo-imp" aria-hidden="true">
        {t.ews_demo_imp}
      </span>
      <span className="ews-demo-ev ews-demo-own" aria-hidden="true">
        {t.ews_demo_own}
      </span>
      <span className="ews-demo-ev ews-demo-prop" aria-hidden="true">
        {t.ews_demo_prop}
      </span>
    </div>
  );
}
