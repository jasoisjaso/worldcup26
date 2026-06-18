import type { Config } from "tailwindcss"

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Surface ramp — page base is darkest so cards lift above it.
        surface: {
          0: "#07090e",
          1: "#0a0e16",
          2: "#0e1420",
          3: "#131a28",
          4: "#18202f",
        },
        edge: {
          subtle: "rgba(255,255,255,0.05)",
          DEFAULT: "#1a2336",
          strong: "#2a3a55",
        },
        ink: {
          DEFAULT: "#e6edf5", // near-white primary text
        },
      },
      boxShadow: {
        e1: "inset 0 1px 0 0 rgba(255,255,255,0.05), 0 2px 8px -2px rgba(0,0,0,0.6)",
        e2: "inset 0 1px 0 0 rgba(255,255,255,0.06), 0 6px 22px -6px rgba(0,0,0,0.72)",
        e3: "0 18px 50px -14px rgba(0,0,0,0.82)",
        glow: "0 0 60px -10px rgba(16,185,129,0.28)",
        "glow-gold": "0 0 60px -10px rgba(251,191,36,0.22)",
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
}

export default config
