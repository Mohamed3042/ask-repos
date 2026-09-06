import { cookies } from "next/headers";

import { AskConsole } from "@/components/AskConsole";
import { DemoLimits } from "@/components/DemoLimits";
import { getCorpus } from "@/lib/api";
import { DEFAULT_LOCALE, LOCALE_COOKIE, dictionaryFor, isLocale } from "@/lib/i18n";

export const dynamic = "force-dynamic";

export default async function AskPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const repoParam = typeof params.repo === "string" ? params.repo : undefined;
  const repo = repoParam && /^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repoParam) ? repoParam : undefined;
  const store = await cookies();
  const raw = store.get(LOCALE_COOKIE)?.value;
  const locale = isLocale(raw) ? raw : DEFAULT_LOCALE;
  const dictionary = dictionaryFor(locale);
  const corpus = await getCorpus();

  return (
    <>
      <div>
        <h1>{dictionary.ask.title}</h1>
        <p className="lede">{dictionary.ask.lede}</p>
      </div>

      {corpus.ok ? (
        <DemoLimits corpus={corpus.corpus} locale={locale} />
      ) : (
        <div className="banner banner-danger" data-testid="demo-limits-error">
          <span aria-hidden="true">✕</span>
          <p>
            <strong>{dictionary.corpus.errorTitle}. </strong>
            {corpus.detail}
          </p>
        </div>
      )}

      {repo ? (
        <p className="small muted" data-testid="repo-scope">
          <span className="tag mono" dir="ltr">
            {repo}
          </span>
        </p>
      ) : null}

      <AskConsole locale={locale} repo={repo} />
    </>
  );
}
