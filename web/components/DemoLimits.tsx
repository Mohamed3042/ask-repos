import { dictionaryFor, type Locale } from "@/lib/i18n";
import type { Corpus } from "@/lib/types";

/**
 * What this deployment will and will not do, stated before anyone asks it anything.
 * Every value is read from the API's own `/v1/corpus`, so the banner cannot drift from
 * the service it is describing.
 */
export function DemoLimits({ corpus, locale }: { corpus: Corpus; locale: Locale }) {
  const dictionary = dictionaryFor(locale);
  const parts = [
    corpus.readonly ? dictionary.demo.readonly : dictionary.demo.writable,
    corpus.rate_limit_per_minute > 0
      ? dictionary.demo.rate(corpus.rate_limit_per_minute)
      : dictionary.demo.noRate,
    dictionary.demo.corpusOwner(corpus.owner),
    dictionary.demo.provider(corpus.generation),
  ];
  return (
    <div className={`banner${corpus.readonly ? "" : " banner-warn"}`} data-testid="demo-limits">
      <span aria-hidden="true">ⓘ</span>
      <p>
        <strong>{dictionary.demo.title}. </strong>
        {corpus.demo_note ? `${corpus.demo_note} ` : ""}
        {parts.join(" ")}
      </p>
    </div>
  );
}
