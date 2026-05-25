import type { Config } from "tailwindcss";

/**
 * Design tokens.
 *
 *   Body:    Public Sans  — adopted by the US Web Design System;
 *            officialdocument feel that fits "audit-ready" without being
 *            a reflex AI font.
 *   Display: Bricolage Grotesque — variable, has slight personality,
 *            not a Google-defaults pick.
 *   Mono:    JetBrains Mono — used only for raw payloads / sha256.
 *
 * Palette is lifted from breatheesg.com source CSS, but neutrals are
 * tinted toward brand-green so surfaces feel cohesive rather than
 * generic ash-gray. Pure white/black are avoided (oklch tints only).
 */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        brand: {
          green: {
            50:  "#F4FAF6",
            100: "#E1F1E5",
            200: "#C7E5CE",
            300: "#97CCA2",
            400: "#5FC272",
            500: "#39B54A", // primary
            600: "#2EA13D",
            700: "#29893D",
            800: "#236E33",
            900: "#1B5728",
          },
          teal:   { 100: "#D6F1F8", 500: "#0BAFD0", 700: "#0A7D95" },
          purple: { 100: "#E8EAF6", 300: "#AFB5DD", 700: "#5B65A1" },
          paper:  "#FAFBFA",
          surface:"#FFFFFE",
          ink:    "#161C28",
          mid:    "#404756",
          subtle: "#727988",
          rule:   "#E3E6E2",
          rule2:  "#EFF1EE",
        },
      },
      fontFamily: {
        sans:    ['"Public Sans"', "ui-sans-serif", "system-ui", "sans-serif"],
        display: ['"Bricolage Grotesque"', '"Public Sans"', "ui-sans-serif", "sans-serif"],
        mono:    ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      fontFeatureSettings: {
        tnum: '"tnum", "lnum"',
      },
      letterSpacing: {
        tightish: "-0.012em",
        widerlabel: "0.08em",
      },
      borderRadius: {
        sm:  "3px",
        DEFAULT: "5px",
        md:  "6px",
        lg:  "8px",
      },
    },
  },
  plugins: [],
} satisfies Config;
