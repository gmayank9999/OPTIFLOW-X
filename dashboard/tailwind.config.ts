import type { Config } from "tailwindcss";

// Every color is a CSS variable (app/globals.css) so light/dark is one
// token swap, never a second set of utility classes.
const token = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      colors: {
        paper: token("paper"),
        surface: token("surface"),
        sunken: token("sunken"),
        ink: token("ink"),
        muted: token("muted"),
        faint: token("faint"),
        rule: token("rule"),
        accent: token("accent"),
        "accent-soft": token("accent-soft"),
        warn: token("warn"),
        "warn-soft": token("warn-soft"),
        bad: token("bad"),
        "bad-soft": token("bad-soft"),
        info: token("info"),
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      fontSize: {
        "2xs": ["10.5px", { lineHeight: "14px", letterSpacing: "0.04em" }],
      },
      borderRadius: { DEFAULT: "6px" },
    },
  },
  plugins: [],
};

export default config;
