import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./lib/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border, 220 13% 91%))",
        input: "hsl(var(--input, 220 13% 91%))",
        ring: "hsl(var(--ring, 238 82% 59%))",
        background: "hsl(var(--background, 220 20% 98%))",
        foreground: "hsl(var(--foreground, 224 71% 4%))",
        brand: {
          50: "#eef2ff",
          100: "#e0e7ff",
          200: "#c7d2fe",
          300: "#a5b4fc",
          400: "#818cf8",
          500: "#6366f1",
          600: "#4f46e5",
          700: "#4338ca",
          800: "#3730a3",
          900: "#312e81",
          950: "#1e1b4b",
        },
        card: {
          DEFAULT: "hsl(var(--card, 0 0% 100%))",
          foreground: "hsl(var(--card-foreground, 224 71% 4%))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted, 220 14.3% 95.9%))",
          foreground: "hsl(var(--muted-foreground, 220 8.9% 46.1%))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent, 220 14.3% 95.9%))",
          foreground: "hsl(var(--accent-foreground, 220.9 39.3% 11%))",
        },
      },
      borderRadius: {
        lg: "var(--radius, 0.75rem)",
        md: "calc(var(--radius, 0.75rem) - 2px)",
        sm: "calc(var(--radius, 0.75rem) - 4px)",
      },
      boxShadow: {
        subtle: "0 1px 2px 0 rgba(0, 0, 0, 0.03), 0 1px 6px -1px rgba(0, 0, 0, 0.02), 0 2px 4px 0 rgba(0, 0, 0, 0.02)",
        glow: "0 0 20px -5px rgba(99, 102, 241, 0.3)",
        card: "0 1px 3px 0 rgba(0, 0, 0, 0.04), 0 1px 2px -1px rgba(0, 0, 0, 0.04)",
      },
      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite",
      },
    },
  },
  plugins: [],
};
export default config;
