import type { Metadata } from "next";
import { NextIntlClientProvider } from "next-intl";
import { getLocale, getMessages } from "next-intl/server";

import "./globals.css";

export const metadata: Metadata = {
  title: "Creator Publishing",
};

/**
 * Root layout.
 *
 * The locale provider sits here rather than in the dashboard layout so that marketing and auth
 * routes are localized too. R13 forbids hardcoded visible strings, and README requires the
 * interface be internationalization-ready from the beginning — retrofitting i18n onto a built
 * interface is how untranslatable strings get shipped.
 */
export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const locale = await getLocale();
  const messages = await getMessages();

  return (
    <html lang={locale}>
      <body>
        <NextIntlClientProvider locale={locale} messages={messages}>
          {children}
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
