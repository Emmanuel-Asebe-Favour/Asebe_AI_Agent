import { useTranslations } from "next-intl";

/**
 * The unified dashboard.
 *
 * README requires customers and administrators to share one dashboard shell — "There must not be
 * separate customer and administrator dashboard applications." So this is one layout with
 * role-aware navigation, not two applications.
 *
 * Two rules are visible in what this file does NOT do:
 *
 * * It does not filter navigation by role to protect anything. R12: "Authorization is enforced
 *   server-side. Hiding a nav link is not authorization." Hiding is a usability affordance; the
 *   protection is the permission dependency on the route.
 * * It does not compute any status, capability, or retry decision. Those arrive from the API,
 *   typed through @asebe/contracts (§6).
 */
export default function DashboardPage() {
  const t = useTranslations("dashboard");

  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">{t("title")}</h1>
      <p className="mt-2 text-sm text-gray-600">{t("subtitle")}</p>
    </main>
  );
}
