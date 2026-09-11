import { getRequestConfig } from "next-intl/server";

/**
 * Locale resolution for the App Router.
 *
 * R13 forbids hardcoded visible strings, and README requires the app be internationalization-ready
 * "from the beginning". This file is what makes that structural rather than aspirational: a
 * component cannot render text without a message key reaching messages/<locale>.json.
 *
 * Locale negotiation is not implemented yet — every request resolves to `en`. README requires a
 * user-selected language, so the next step is to read the locale from the user's settings
 * (README's User data model has `preferred_language`) with an `Accept-Language` fallback.
 */
export default getRequestConfig(async () => {
  const locale = "en";

  return {
    locale,
    messages: (await import(`../../messages/${locale}.json`)).default,
  };
});
