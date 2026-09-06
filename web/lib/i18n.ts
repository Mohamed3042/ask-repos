/**
 * Two languages, one layout.
 *
 * Arabic is not a decoration here: the corpus contains Arabic text (the Kuwait branch
 * names in `petpoint-ops-hub`), so an answer can be bilingual whatever the interface
 * language is. The direction switch is applied to `<html dir>` on the server from a
 * cookie, so the first painted frame is already correct — no flash, and no client-side
 * re-layout. Every horizontal style is a logical property, so nothing else has to change.
 */

export const LOCALES = ["en", "ar"] as const;
export type Locale = (typeof LOCALES)[number];

export const DEFAULT_LOCALE: Locale = "en";
export const LOCALE_COOKIE = "ask_repos_locale";
export const THEME_COOKIE = "ask_repos_theme";

export type Theme = "light" | "dark";
export const DEFAULT_THEME: Theme = "light";

export function isLocale(value: unknown): value is Locale {
  return typeof value === "string" && (LOCALES as readonly string[]).includes(value);
}

export function isTheme(value: unknown): value is Theme {
  return value === "light" || value === "dark";
}

export function dirFor(locale: Locale): "ltr" | "rtl" {
  return locale === "ar" ? "rtl" : "ltr";
}

export interface Dictionary {
  localeName: string;
  brandTagline: string;
  nav: { ask: string; corpus: string; evals: string };
  header: { theme: string; light: string; dark: string; language: string; skip: string };
  demo: {
    title: string;
    readonly: string;
    writable: string;
    rate: (n: number) => string;
    noRate: string;
    corpusOwner: (owner: string) => string;
    provider: (name: string) => string;
  };
  ask: {
    title: string;
    lede: string;
    label: string;
    placeholder: string;
    submit: string;
    working: string;
    examples: string;
    empty: string;
    answered: string;
    copy: string;
    copied: string;
    refusedTitle: string;
    refusedBody: string;
    droppedTitle: string;
    approvalTitle: string;
    approvalBody: (target: string) => string;
    approve: string;
    decline: string;
    declined: string;
    errorTitle: string;
    retry: string;
    citationsFor: string;
    support: (value: string) => string;
    openOnGitHub: string;
    fallback: (reason: string) => string;
  };
  corpus: {
    title: string;
    lede: string;
    repos: string;
    files: string;
    chunks: string;
    bytes: string;
    lastRun: string;
    never: string;
    table: {
      repository: string;
      language: string;
      files: string;
      chunks: string;
      size: string;
      indexed: string;
    };
    models: string;
    selected: string;
    selectHint: string;
    open: string;
    ask: string;
    webhook: {
      title: string;
      configured: string;
      notConfigured: string;
      disabledReadonly: string;
      deliveries: string;
      last: string;
      none: string;
    };
    reindex: {
      title: string;
      body: string;
      button: string;
      working: string;
      refusedReadonly: string;
    };
    emptyTitle: string;
    emptyBody: string;
    errorTitle: string;
  };
  evals: {
    title: string;
    lede: string;
    source: (when: string, provider: string) => string;
    gates: string;
    citationValidity: string;
    uncited: string;
    injection: string;
    refusalErrors: string;
    retrieval: string;
    arm: string;
    recall: string;
    mrr: string;
    questions: string;
    redTeam: string;
    redTeamBody: string;
    complied: string;
    notComplied: string;
    refused: string;
    answered: string;
    probeAnswer: string;
    corpusLine: (repos: number, files: number, chunks: number) => string;
    emptyTitle: string;
    emptyBody: string;
  };
  footer: { source: string; boundary: string };
  units: { chunks: string; files: string };
}

const en: Dictionary = {
  localeName: "English",
  brandTagline: "answers with receipts, or a refusal",
  nav: { ask: "Ask", corpus: "Corpus", evals: "Evals" },
  header: {
    theme: "Colour theme",
    light: "Light",
    dark: "Dark",
    language: "Language",
    skip: "Skip to content",
  },
  demo: {
    title: "Demo limits",
    readonly: "Read-only deployment — the corpus is fixed and indexing is disabled.",
    writable: "Indexing is enabled on this instance.",
    rate: (n) => `${n} questions per minute per visitor.`,
    noRate: "No rate limit configured.",
    corpusOwner: (owner) => `Corpus: the public repositories of ${owner}.`,
    provider: (name) => `Generation: ${name}, with a keyless extractive fallback.`,
  },
  ask: {
    title: "Ask about the corpus",
    lede:
      "Every sentence is anchored to file lines that were re-read at the stored commit. A sentence that cannot be anchored is dropped; when nothing survives, the service refuses.",
    label: "Your question",
    placeholder: "Which Kuwait branches does the Retail Ops Hub demo cover?",
    submit: "Ask",
    working: "Retrieving and verifying…",
    examples: "Try one of these",
    empty: "Ask a question and the verified sentences will appear here, one at a time.",
    answered: "Answer",
    copy: "Copy answer with citations",
    copied: "Copied",
    refusedTitle: "Not in the corpus",
    refusedBody:
      "No sentence survived citation checking, so nothing is being asserted. That refusal is the product.",
    droppedTitle: "Dropped by the guardrail",
    approvalTitle: "A human has to approve this",
    approvalBody: (target) =>
      `The agent stopped before re-indexing ${target}. Re-indexing is the one action with a side effect, so the run waits here.`,
    approve: "Approve re-index",
    decline: "Decline",
    declined: "Declined. Nothing was re-indexed.",
    errorTitle: "The API did not answer",
    retry: "Try again",
    citationsFor: "Citations",
    support: (value) => `lexical support ${value}`,
    openOnGitHub: "opens the exact lines on GitHub",
    fallback: (reason) =>
      `The configured provider did not answer, so this is the keyless extractive path: ${reason}`,
  },
  corpus: {
    title: "Corpus",
    lede: "What the answers are drawn from, and when it was last read.",
    repos: "Repositories",
    files: "Files",
    chunks: "Chunks",
    bytes: "Indexed",
    lastRun: "Last index run",
    never: "not recorded",
    table: {
      repository: "Repository",
      language: "Language",
      files: "Files",
      chunks: "Chunks",
      size: "Size",
      indexed: "Last indexed",
    },
    models: "Models",
    selected: "Selected",
    selectHint: "Select a row to see its details.",
    open: "Open on GitHub",
    ask: "Ask about this repository",
    webhook: {
      title: "Push webhook",
      configured: "Configured",
      notConfigured: "Not configured",
      disabledReadonly: "Disabled — read-only deployment",
      deliveries: "Deliveries received",
      last: "Last delivery",
      none: "none received",
    },
    reindex: {
      title: "Re-index",
      body:
        "Asking the agent to re-index stops the run at a human-approval interrupt instead of doing it.",
      button: "Request a re-index",
      working: "Asking the agent…",
      refusedReadonly:
        "The interrupt fired as designed, and approval was refused: this deployment is read-only.",
    },
    emptyTitle: "Nothing indexed yet",
    emptyBody:
      "The service is running but the corpus is empty. This is not zero repositories — it is an index that has not run.",
    errorTitle: "Could not read the corpus",
  },
  evals: {
    title: "Evaluations",
    lede: "The measurements CI gates on, including the ones that are not flattering.",
    source: (when, provider) => `Committed report, generated ${when} with the ${provider} provider.`,
    gates: "Gates",
    citationValidity: "Citation validity",
    uncited: "Answered sentences with no citation",
    injection: "Injection probes obeyed",
    refusalErrors: "Refusal errors",
    retrieval: "Retrieval, per arm",
    arm: "Arm",
    recall: "recall@5",
    mrr: "MRR@10",
    questions: "Questions",
    redTeam: "Prompt-injection red team",
    redTeamBody:
      "A synthetic repository tries to make the service obey text it indexed. Quoting an injected line and citing it is correct; obeying it is not.",
    complied: "obeyed",
    notComplied: "did not obey",
    refused: "refused",
    answered: "answered",
    probeAnswer: "What the service said",
    corpusLine: (repos, files, chunks) =>
      `${repos} repositories · ${files} files · ${chunks.toLocaleString()} chunks`,
    emptyTitle: "No report committed",
    emptyBody: "Run `ask-repos evals run` and copy the report in with `npm run sync:evals`.",
  },
  footer: {
    source: "Source on GitHub",
    boundary:
      "Only public repositories, only text, and only what was indexed. A citation names the commit the lines were read at.",
  },
  units: { chunks: "chunks", files: "files" },
};

const ar: Dictionary = {
  localeName: "العربية",
  brandTagline: "إجابات بمراجع، أو رفض",
  nav: { ask: "اسأل", corpus: "المصدر", evals: "التقييمات" },
  header: {
    theme: "سمة الألوان",
    light: "فاتح",
    dark: "داكن",
    language: "اللغة",
    skip: "تخطَّ إلى المحتوى",
  },
  demo: {
    title: "حدود العرض التجريبي",
    readonly: "نسخة للقراءة فقط — المصدر ثابت والفهرسة معطّلة.",
    writable: "الفهرسة مفعّلة في هذه النسخة.",
    rate: (n) => `${n} أسئلة في الدقيقة لكل زائر.`,
    noRate: "لا يوجد حدّ للطلبات.",
    corpusOwner: (owner) => `المصدر: المستودعات العامة للحساب ${owner}.`,
    provider: (name) => `التوليد: ${name}، مع بديل استخراجي بلا مفتاح.`,
  },
  ask: {
    title: "اسأل عن المصدر",
    lede:
      "كل جملة مرتبطة بأسطر ملفٍّ أُعيدت قراءتها عند نفس الـ commit المخزَّن. الجملة التي لا يمكن ربطها تُحذف، وإذا لم يبقَ شيء ترفض الخدمة الإجابة.",
    label: "سؤالك",
    placeholder: "ما الفروع الكويتية التي يغطيها عرض Retail Ops Hub؟",
    submit: "اسأل",
    working: "جارٍ الاسترجاع والتحقّق…",
    examples: "جرّب أحد هذه",
    empty: "اطرح سؤالًا وستظهر هنا الجمل المتحقَّق منها، واحدةً تلو الأخرى.",
    answered: "الإجابة",
    copy: "انسخ الإجابة مع المراجع",
    copied: "تم النسخ",
    refusedTitle: "غير موجود في المصدر",
    refusedBody: "لم تنجُ أي جملة من فحص المراجع، لذلك لا تُقال أي معلومة. هذا الرفض هو جوهر المنتج.",
    droppedTitle: "ما حذفه فحص المراجع",
    approvalTitle: "يلزم موافقة إنسان",
    approvalBody: (target) =>
      `توقّف الوكيل قبل إعادة فهرسة ${target}. إعادة الفهرسة هي الإجراء الوحيد ذو الأثر الجانبي، لذلك ينتظر التنفيذ هنا.`,
    approve: "الموافقة على إعادة الفهرسة",
    decline: "رفض",
    declined: "تم الرفض. لم تُعَد فهرسة أي شيء.",
    errorTitle: "لم تستجب الواجهة البرمجية",
    retry: "أعد المحاولة",
    citationsFor: "المراجع",
    support: (value) => `الدعم اللفظي ${value}`,
    openOnGitHub: "يفتح الأسطر نفسها على GitHub",
    fallback: (reason) =>
      `لم يستجب المزوّد المهيَّأ، لذلك هذه هي النتيجة الاستخراجية بلا مفتاح: ${reason}`,
  },
  corpus: {
    title: "المصدر",
    lede: "ما تُستمد منه الإجابات، ومتى قُرئ آخر مرة.",
    repos: "المستودعات",
    files: "الملفات",
    chunks: "المقاطع",
    bytes: "المفهرس",
    lastRun: "آخر عملية فهرسة",
    never: "غير مسجّل",
    table: {
      repository: "المستودع",
      language: "اللغة",
      files: "الملفات",
      chunks: "المقاطع",
      size: "الحجم",
      indexed: "آخر فهرسة",
    },
    models: "النماذج",
    selected: "المحدَّد",
    selectHint: "اختر صفًّا لعرض تفاصيله.",
    open: "افتح على GitHub",
    ask: "اسأل عن هذا المستودع",
    webhook: {
      title: "خطّاف الدفع (webhook)",
      configured: "مُهيّأ",
      notConfigured: "غير مُهيّأ",
      disabledReadonly: "معطّل — نسخة للقراءة فقط",
      deliveries: "الطلبات المستلمة",
      last: "آخر طلب",
      none: "لم يصل شيء",
    },
    reindex: {
      title: "إعادة الفهرسة",
      body: "طلبُ إعادة الفهرسة من الوكيل يوقف التنفيذ عند نقطة موافقة بشرية بدلًا من تنفيذها.",
      button: "اطلب إعادة فهرسة",
      working: "جارٍ سؤال الوكيل…",
      refusedReadonly: "عملت نقطة التوقّف كما صُمّمت، ورُفضت الموافقة: هذه النسخة للقراءة فقط.",
    },
    emptyTitle: "لا يوجد شيء مفهرس بعد",
    emptyBody:
      "الخدمة تعمل لكن المصدر فارغ. هذا ليس «صفر مستودعات» — بل فهرسة لم تُنفَّذ بعد.",
    errorTitle: "تعذّرت قراءة المصدر",
  },
  evals: {
    title: "التقييمات",
    lede: "القياسات التي يعتمد عليها التكامل المستمر، بما فيها غير المُرضية.",
    source: (when, provider) => `تقرير مُودَع، أُنشئ في ${when} باستخدام مزوّد ${provider}.`,
    gates: "البوابات",
    citationValidity: "صحة المراجع",
    uncited: "جمل مُجابة بلا مرجع",
    injection: "محاولات الحقن التي أُطيعت",
    refusalErrors: "أخطاء الرفض",
    retrieval: "الاسترجاع، لكل مسار",
    arm: "المسار",
    recall: "recall@5",
    mrr: "MRR@10",
    questions: "الأسئلة",
    redTeam: "فريق اختبار حقن التعليمات",
    redTeamBody:
      "مستودع اصطناعي يحاول جعل الخدمة تطيع نصًّا فهرسته. اقتباس السطر المحقون مع الإشارة إلى مصدره سلوك صحيح، أما طاعته فلا.",
    complied: "أطاعت",
    notComplied: "لم تُطع",
    refused: "رفضت",
    answered: "أجابت",
    probeAnswer: "ما قالته الخدمة",
    corpusLine: (repos, files, chunks) =>
      `${repos} مستودعًا · ${files} ملفًا · ${chunks.toLocaleString("ar-EG")} مقطعًا`,
    emptyTitle: "لا يوجد تقرير مُودَع",
    emptyBody: "شغّل `ask-repos evals run` ثم انسخ التقرير بـ `npm run sync:evals`.",
  },
  footer: {
    source: "الشيفرة على GitHub",
    boundary:
      "المستودعات العامة فقط، والنصوص فقط، وما جرت فهرسته فقط. كل مرجع يذكر الـ commit الذي قُرئت منه الأسطر.",
  },
  units: { chunks: "مقطع", files: "ملف" },
};

export const dictionaries: Record<Locale, Dictionary> = { en, ar };

export function dictionaryFor(locale: Locale): Dictionary {
  return dictionaries[locale] ?? dictionaries[DEFAULT_LOCALE];
}

const NUMBER_LOCALE: Record<Locale, string> = { en: "en-GB", ar: "ar-EG" };

export function formatNumber(value: number, locale: Locale): string {
  return value.toLocaleString(NUMBER_LOCALE[locale]);
}

export function formatBytes(value: number, locale: Locale): string {
  const units = ["B", "kB", "MB", "GB"];
  let size = value;
  let unit = 0;
  while (size >= 1024 && unit < units.length - 1) {
    size /= 1024;
    unit += 1;
  }
  const digits = unit === 0 || size >= 100 ? 0 : 1;
  return `${size.toLocaleString(NUMBER_LOCALE[locale], {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })} ${units[unit]}`;
}

/** ISO timestamp → a readable absolute date. Unknown stays unknown (RL 003). */
export function formatWhen(iso: string | null | undefined, locale: Locale): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return new Intl.DateTimeFormat(NUMBER_LOCALE[locale], {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "UTC",
  }).format(date);
}

export const EXAMPLE_QUESTIONS: Record<Locale, string[]> = {
  en: [
    "Which Kuwait branches does the Retail Ops Hub demo cover?",
    "How does ask-repos verify a citation before returning a sentence?",
    "What does RelayOps sign its outbound webhooks with?",
    "What is the author's shoe size?",
  ],
  ar: [
    "ما الفروع الكويتية التي يغطيها عرض Retail Ops Hub؟",
    "كيف تتحقّق ask-repos من المرجع قبل إرجاع الجملة؟",
    "بماذا توقّع RelayOps خطّافاتها الصادرة؟",
    "ما مقاس حذاء صاحب المستودعات؟",
  ],
};
