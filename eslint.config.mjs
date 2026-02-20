// @ts-check

import eslint from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";

export default tseslint.config(
  eslint.configs.recommended,
  ...tseslint.configs.recommended,
  ...tseslint.configs.stylistic,
  // React / browser JS: declare browser globals, enforce Rules of Hooks,
  // and disable TypeScript-specific rules that don't apply to plain JS.
  {
    files: ["**/*.{js,jsx}"],
    plugins: { "react-hooks": reactHooks },
    languageOptions: {
      globals: globals.browser,
      parserOptions: {
        ecmaFeatures: { jsx: true },
        sourceType: "module",
      },
    },
    rules: {
      "react-hooks/rules-of-hooks": "error",
      "react-hooks/exhaustive-deps": "warn",
      // Disable TS-specific rules for plain JS — use base ESLint equivalents
      "@typescript-eslint/no-unused-vars": "off",
      "@typescript-eslint/no-empty-function": "off",
      "no-unused-vars": ["warn", { varsIgnorePattern: "^[A-Z_]" }],
    },
  },
);
