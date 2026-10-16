import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        navy: {
          50: "#f3f6fb",
          100: "#e4eaf4",
          200: "#c9d4e7",
          300: "#9fb2d2",
          400: "#6f89b6",
          500: "#4b679a",
          600: "#3a517e",
          700: "#2f4166",
          800: "#223050",
          900: "#172238",
          950: "#0e1626",
        },
        accent: { DEFAULT: "#2a78d6", dark: "#1c5cab", light: "#cde2fb" },
        surface: "#fcfcfb",
        page: "#f5f6f8",
        ink: { DEFAULT: "#0b0b0b", secondary: "#52514e", muted: "#6b6a65" },
        status: { good: "#0ca30c", warning: "#fab219", serious: "#ec835a", critical: "#d03b3b" },
      },
      fontFamily: {
        sans: ["system-ui", "-apple-system", "Segoe UI", "Roboto", "sans-serif"],
      },
      boxShadow: { card: "0 1px 2px rgba(16,24,40,0.05)" },
    },
  },
  plugins: [],
} satisfies Config;
