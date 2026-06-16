import type { Config } from "tailwindcss"

const config: Config = {
  darkMode: "class",
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Ink-navy ramp (blue-tinted dark, not flat black). Page is darkest; cards lift.
        surface: {
          0: "#080b12",
          1: "#0d1220",
          2: "#121a2c",
          3: "#18233a",
          4: "#1f2e4a",
        },
        edge: {
          subtle: "rgba(148,176,255,0.07)",
          DEFAULT: "#243352",
          strong: "#35507f",
        },
        ink: {
          DEFAULT: "#eaf1ff", // primary text, faint cool cast
          dim: "#9db0d0",     // labels
          faint: "#5e7099",   // overlines / muted
        },
        // Pitch Amber — the brand/floodlight accent (locked site-wide). Mirrors Tailwind
        // `amber-*` shades so the emerald->amber swap drops in cleanly.
        accent: {
          DEFAULT: "#ffb000",
          bright: "#ffc233",
          deep: "#c97e00",
        },
        // Semantic data colours only (never brand): win / loss / draw, EV +/-.
        pos: "#34d399",
        neg: "#f25c6e",
        draw: "#94a3b8",
      },
      borderRadius: {
        card: "14px",
        panel: "20px",
      },
      boxShadow: {
        e1: "inset 0 1px 0 0 rgba(148,176,255,0.07), 0 2px 10px -4px rgba(0,0,0,0.7)",
        e2: "inset 0 1px 0 0 rgba(148,176,255,0.09), 0 12px 34px -10px rgba(0,0,0,0.78)",
        flood: "0 0 0 1px rgba(255,176,0,0.18), 0 0 70px -12px rgba(255,176,0,0.35)",
        "flood-team": "0 0 70px -14px var(--team-a, rgba(255,176,0,0.35))",
      },
      fontFamily: {
        display: ["var(--font-display)", "system-ui", "sans-serif"],
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-display)", "ui-monospace", "monospace"],
      },
    },
  },
  plugins: [],
}

export default config
