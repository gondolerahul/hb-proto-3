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
    {
      /**
       * `LegacyBackground.tsx` is not authored code. It is the owner's approved
       * background carried across byte-for-byte (D2), and
       * `tests/background_verbatim.test.ts` goes red the moment it stops being
       * identical to `frontend/src/components/layout/AnimatedBackground.tsx`.
       *
       * Its one `exhaustive-deps` finding — a ref read in an effect cleanup — is
       * therefore unactionable by construction: the edit that silences it is the
       * edit that destroys the property the file exists to prove. It is silenced
       * here rather than in the file because a disable comment is itself a byte
       * change, and would fail the same test.
       *
       * Scoped to this one frozen file and this one rule. It grants nothing about
       * three.js: the file sits inside `renderers/world/` and is bound by the
       * confinement above exactly like every other module there.
       */
      files: ["src/renderers/world/LegacyBackground.tsx"],
      rules: { "react-hooks/exhaustive-deps": "off" },
    },
  ],
};
