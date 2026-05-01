import type { Config } from "tailwindcss"

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Block type colors from the mockups
        block: {
          trigger: { bg: "#EFF6FF", border: "#93C5FD", label: "#1D4ED8" },
          brain:   { bg: "#F5F3FF", border: "#A78BFA", label: "#6D28D9" },
          tool:    { bg: "#F0FDF4", border: "#86EFAC", label: "#15803D" },
          logic:   { bg: "#F9FAFB", border: "#D1D5DB", label: "#374151" },
          memory:  { bg: "#FFFBEB", border: "#FCD34D", label: "#92400E" },
          approval:{ bg: "#FFF7ED", border: "#FDBA74", label: "#C2410C" },
          output:  { bg: "#FFF1F2", border: "#FDA4AF", label: "#BE123C" },
          cleanup: { bg: "#FEFCE8", border: "#FDE047", label: "#713F12" },
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
}

export default config
