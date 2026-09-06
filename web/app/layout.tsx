import type { Metadata, Viewport } from "next";
import { cookies } from "next/headers";

import { SiteHeader } from "@/components/SiteHeader";
import {
  DEFAULT_LOCALE,
  DEFAULT_THEME,
  LOCALE_COOKIE,
  THEME_COOKIE,
  dictionaryFor,
  dirFor,
  isLocale,
  isTheme,
} from "@/lib/i18n";

import "./globals.css";

export const metadata: Metadata = {
  title: "ask-repos — answers with receipts",
  description:
    "Ask a GitHub account about its public repositories. Every sentence cites file and line, verified at the stored commit, or the service refuses.",
  authors: [{ name: "Mohamed Mahmoud", url: "https://github.com/Mohamed3042" }],
};

export const viewport: Viewport = {
  themeColor: [
    { media: "(prefers-color-scheme: light)", color: "#f5f7f6" },
    { media: "(prefers-color-scheme: dark)", color: "#0c1211" },
  ],
};

/**
 * Locale and theme are read on the server from cookies, so `<html lang dir data-theme>`
 * is correct in the first byte of HTML. Nothing flashes and nothing re-lays-out: the
 * Arabic build is right-to-left before any JavaScript runs.
 */
export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const store = await cookies();
  const rawLocale = store.get(LOCALE_COOKIE)?.value;
  const rawTheme = store.get(THEME_COOKIE)?.value;
  const locale = isLocale(rawLocale) ? rawLocale : DEFAULT_LOCALE;
  const theme = isTheme(rawTheme) ? rawTheme : DEFAULT_THEME;
  const dictionary = dictionaryFor(locale);

  return (
    <html lang={locale} dir={dirFor(locale)} data-theme={theme}>
      <body>
        <a className="skip" href="#main">
          {dictionary.header.skip}
        </a>
        <div className="shell">
          <SiteHeader locale={locale} theme={theme} />
          <main id="main" className="wrap page" tabIndex={-1}>
            {children}
          </main>
          <footer className="site-footer">
            <div className="wrap row">
              <p className="small" style={{ margin: 0 }}>
                {dictionary.footer.boundary}
              </p>
              <a
                className="small"
                href="https://github.com/Mohamed3042/ask-repos"
                rel="noreferrer noopener"
                target="_blank"
              >
                {dictionary.footer.source} ↗
              </a>
            </div>
          </footer>
        </div>
      </body>
    </html>
  );
}
