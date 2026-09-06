import Link from "next/link";

import { PreferenceToggles } from "@/components/PreferenceToggles";
import { NavLink } from "@/components/NavLink";
import { dictionaryFor, type Locale, type Theme } from "@/lib/i18n";

const VERSION = process.env.NEXT_PUBLIC_UI_VERSION ?? "0.2.0";

export function SiteHeader({ locale, theme }: { locale: Locale; theme: Theme }) {
  const dictionary = dictionaryFor(locale);
  return (
    <header className="site-header">
      <div className="wrap header-row">
        <Link className="brand" href="/">
          <span className="dot" aria-hidden="true" />
          ask-repos
          {/* PROTOCOL: any app with a UI ships a visible version badge. */}
          <span className="version" title="UI version">
            v{VERSION}
          </span>
        </Link>
        <nav className="nav" aria-label={dictionary.nav.ask}>
          <NavLink href="/">{dictionary.nav.ask}</NavLink>
          <NavLink href="/corpus">{dictionary.nav.corpus}</NavLink>
          <NavLink href="/evals">{dictionary.nav.evals}</NavLink>
        </nav>
        <div className="header-tools">
          <PreferenceToggles locale={locale} theme={theme} />
        </div>
      </div>
    </header>
  );
}
