import { useTranslations } from "next-intl";

/**
 * Marketing landing page.
 *
 * AGENTS.md §5 places one hard rule on everything under apps/web:
 *
 *   "apps/web must never contain a business rule. If you are writing an `if` about publishing
 *    status, retry eligibility, or platform capability in a React component, it belongs in the API
 *    or the response shape."
 *
 * So this page renders text and links. It decides nothing.
 *
 * Strings come from messages/en.json via `useTranslations` rather than appearing inline — R13.
 */
export default function HomePage() {
  const t = useTranslations("common");

  return (
    <main className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center gap-4 p-8">
      <h1 className="text-3xl font-semibold">{t("appName")}</h1>
    </main>
  );
}
