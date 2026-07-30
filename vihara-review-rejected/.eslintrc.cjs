/**
 * Vihara's boundary lints (D1 §1, §3). Two rules carry the architecture:
 *
 * 1. Nothing imports from frontend/ — a single convenience import would
 *    silently make the two apps one app (the LEARN⇸SEGA lesson: the first
 *    violation is always reasonable, and by the third the property is gone).
 * 2. Only the World renderer's directories may import three.js — one
 *    careless static import from a shared module pulls the whole 3D stack
 *    into the tier-C bundle and nothing about the app *looks* wrong
 *    afterwards (D7 §3.3).
 */
module.exports = {
  root: true,
  env: { browser: true, es2022: true },
  parser: "@typescript-eslint/parser",
  parserOptions: { ecmaVersion: 2022, sourceType: "module" },
  plugins: ["@typescript-eslint", "react-hooks"],
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
  ],
  ignorePatterns: ["dist", "node_modules", "*.cjs", "*.mjs"],
  rules: {
    "no-restricted-imports": [
      "error",
      {
        patterns: [
          {
            group: ["**/frontend/**", "@/legacy/**"],
            message:
              "vihara/ shares nothing with frontend/ — rebuild it here (D1 §1).",
          },
          {
            group: ["three", "three/**", "@react-three/**"],
            message:
              "Only components/world/ and renderers/world/ may import three.js (D7 §3.3).",
          },
        ],
      },
    ],
  },
  overrides: [
    {
      files: [
        "src/components/world/**/*.{ts,tsx}",
        "src/renderers/world/**/*.{ts,tsx}",
      ],
      rules: {
        "no-restricted-imports": [
          "error",
          {
            patterns: [
              {
                group: ["**/frontend/**", "@/legacy/**"],
                message:
                  "vihara/ shares nothing with frontend/ — rebuild it here (D1 §1).",
              },
            ],
          },
        ],
      },
    },
  ],
};
