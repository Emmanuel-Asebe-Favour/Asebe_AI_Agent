import type { Config } from "tailwindcss";

/**
 * Tailwind configuration.
 *
 * `content` is scoped to `src/` deliberately. A glob that scans the whole repository slows the
 * build and, worse, picks up class-like strings from generated files and documentation — producing
 * CSS for classes that do not exist. The contract file is excluded for exactly that reason.
 */
const config: Config = {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {},
  },
  plugins: [],
};

export default config;
