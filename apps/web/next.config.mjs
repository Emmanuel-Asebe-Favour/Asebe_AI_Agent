import createNextIntlPlugin from "next-intl/plugin";

/**
 * Next.js configuration.
 *
 * `transpilePackages` is required because @asebe/contracts is consumed as TypeScript source rather
 * than a build artifact. Generating and shipping a compiled bundle for a types-only package would
 * add a build step whose only output is types, and the contract rule (AGENTS.md §6) is about the
 * *schema* being generated, not the wrapper.
 */
const nextConfig = {
  reactStrictMode: true,
  transpilePackages: ["@asebe/contracts"],
  typescript: {
    // A type error must fail the build. Next.js defaults this to failing only on production
    // builds; the whole point of the contract rule is that a type mismatch is a real defect.
    ignoreBuildErrors: false,
  },
};

const withNextIntl = createNextIntlPlugin("./src/i18n/request.ts");

export default withNextIntl(nextConfig);
