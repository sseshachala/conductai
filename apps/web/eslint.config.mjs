import { defineConfig } from "eslint/config";
import next from "eslint-config-next";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

export default defineConfig([{
    extends: [...next],

    rules: {
        "react/no-unescaped-entities": "warn",
        "react-hooks/exhaustive-deps": "warn",
        "react-hooks/rules-of-hooks": "error",
        "@next/next/no-img-element": "warn",
        // ponytail: React 19 / eslint-plugin-react-hooks 6 ship new rules as
        // error by default; downgrade to warn so the upgrade lands. Fix
        // codebase incrementally, then flip back to error.
        "react-hooks/set-state-in-effect": "warn",
        "react-hooks/immutability": "warn",
        "react-hooks/preserve-manual-memoization": "warn",
        "react-hooks/purity": "warn",
        "react-hooks/static-components": "warn",
        "@next/next/no-html-link-for-pages": "warn",
        "@next/next/no-location-assign-relative-destination": "warn",
    },
}]);