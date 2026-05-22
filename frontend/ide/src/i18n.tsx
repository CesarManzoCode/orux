import {
  createContext, useContext, useState, useCallback,
  type ReactNode,
} from "react";
import { es } from "./i18n.es";
import { en } from "./i18n.en";

export type Lang = "es" | "en";
const KEY = "orux_lang";

function cargaLang(): Lang {
  try { return (localStorage.getItem(KEY) as Lang) || "es"; }
  catch { return "es"; }
}

/* ─── Traducciones ────────────────────────────────────────────────────────── */
// Los diccionarios viven en i18n.es.ts / i18n.en.ts — un archivo de datos por
// idioma. Acá solo se recombinan: `T` y el tipo `Traducciones` conservan su
// forma, así que los componentes (useI18n) no se enteran del corte.
export const T = { es, en } as const;

export type Traducciones = (typeof T)[Lang];

/* ─── Contexto ────────────────────────────────────────────────────────────── */
interface I18nCtx {
  lang: Lang;
  t: Traducciones;
  setLang: (l: Lang) => void;
}

const Ctx = createContext<I18nCtx>({
  lang: "es",
  t: T.es,
  setLang: () => {},
});

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(cargaLang);

  const setLang = useCallback((l: Lang) => {
    try { localStorage.setItem(KEY, l); } catch {}
    setLangState(l);
  }, []);

  return (
    <Ctx.Provider value={{ lang, t: T[lang], setLang }}>
      {children}
    </Ctx.Provider>
  );
}

export function useI18n() { return useContext(Ctx); }

/* Selector de idioma reutilizable — pill compacta con las dos opciones. */
export function LangToggle({ className = "" }: { className?: string }) {
  const { lang, setLang } = useI18n();
  return (
    <span
      className={"lang-toggle " + className}
      role="group"
      aria-label="idioma / language"
    >
      <button
        className={lang === "es" ? "lt-active" : ""}
        aria-pressed={lang === "es"}
        onClick={() => setLang("es")}
      >ES</button>
      <button
        className={lang === "en" ? "lt-active" : ""}
        aria-pressed={lang === "en"}
        onClick={() => setLang("en")}
      >EN</button>
    </span>
  );
}
