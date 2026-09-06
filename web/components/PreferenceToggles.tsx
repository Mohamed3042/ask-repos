"use client";

import { useRouter } from "next/navigation";
import { useTransition } from "react";

import {
  LOCALE_COOKIE,
  LOCALES,
  THEME_COOKIE,
  dictionaryFor,
  type Locale,
  type Theme,
} from "@/lib/i18n";

const ONE_YEAR = 60 * 60 * 24 * 365;

function persist(name: string, value: string) {
  document.cookie = `${name}=${value}; path=/; max-age=${ONE_YEAR}; samesite=lax`;
}

/**
 * Language and theme are server state (a cookie read in the root layout), so the toggles
 * write the cookie and ask the server for a fresh render. The document element is updated
 * optimistically first, so the switch is instant even before the refresh lands.
 */
export function PreferenceToggles({ locale, theme }: { locale: Locale; theme: Theme }) {
  const router = useRouter();
  const [pending, startTransition] = useTransition();
  const dictionary = dictionaryFor(locale);

  function chooseLocale(next: Locale) {
    if (next === locale) return;
    persist(LOCALE_COOKIE, next);
    document.documentElement.lang = next;
    document.documentElement.dir = next === "ar" ? "rtl" : "ltr";
    startTransition(() => router.refresh());
  }

  function chooseTheme(next: Theme) {
    if (next === theme) return;
    persist(THEME_COOKIE, next);
    document.documentElement.dataset.theme = next;
    startTransition(() => router.refresh());
  }

  return (
    <>
      <div className="toggle-group" role="group" aria-label={dictionary.header.language}>
        {LOCALES.map((candidate) => (
          <button
            key={candidate}
            type="button"
            lang={candidate}
            aria-pressed={candidate === locale}
            aria-busy={pending || undefined}
            onClick={() => chooseLocale(candidate)}
          >
            {dictionaryFor(candidate).localeName}
          </button>
        ))}
      </div>
      <div className="toggle-group" role="group" aria-label={dictionary.header.theme}>
        <button
          type="button"
          aria-pressed={theme === "light"}
          onClick={() => chooseTheme("light")}
        >
          <span aria-hidden="true">☀</span>
          <span className="sr-only-label"> {dictionary.header.light}</span>
        </button>
        <button type="button" aria-pressed={theme === "dark"} onClick={() => chooseTheme("dark")}>
          <span aria-hidden="true">☾</span>
          <span className="sr-only-label"> {dictionary.header.dark}</span>
        </button>
      </div>
    </>
  );
}
