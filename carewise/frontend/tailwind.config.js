/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Calm, warm palette — designed for users in distress.
        // Avoids the cold blue of typical SaaS chat UIs.
        sand: {
          50: "#FAF7F2",
          100: "#F4EFE6",
          200: "#E8DFCE",
          300: "#D9CBB1",
          400: "#C4AE89",
          500: "#A98E62",
        },
        sage: {
          50: "#F1F4F0",
          100: "#DDE6DA",
          200: "#BACFB6",
          300: "#90B28C",
          400: "#6A9468",
          500: "#4F7A4E",
          600: "#3D5F3D",
          700: "#2F4A30",
        },
        clay: {
          50: "#FBF4F0",
          100: "#F4E2D8",
          200: "#E5C2B0",
          300: "#D29A82",
          400: "#B8755A",
          500: "#965340",
        },
        ink: {
          900: "#1F1B16",
          800: "#2E2820",
          700: "#48413A",
          600: "#6E6760",
          500: "#716A62", // darkened from #928B83 to meet WCAG AA (4.5:1) for small text
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "-apple-system", "sans-serif"],
        serif: ["'Source Serif 4'", "Georgia", "serif"],
      },
      boxShadow: {
        soft: "0 1px 2px rgba(31, 27, 22, 0.04), 0 4px 12px rgba(31, 27, 22, 0.04)",
        lift: "0 2px 4px rgba(31, 27, 22, 0.06), 0 12px 28px rgba(31, 27, 22, 0.08)",
      },
      animation: {
        "fade-in": "fadeIn 300ms ease-out",
        "slide-up": "slideUp 350ms cubic-bezier(0.16, 1, 0.3, 1)",
        "pulse-soft": "pulseSoft 2.5s ease-in-out infinite",
        "pop-in": "popIn 400ms cubic-bezier(0.34, 1.56, 0.64, 1)",
        "check-pop": "checkPop 380ms cubic-bezier(0.34, 1.56, 0.64, 1)",
        "count-up": "countUp 500ms ease-out",
      },
      keyframes: {
        fadeIn: { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        slideUp: {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        pulseSoft: {
          "0%, 100%": { opacity: "0.5" },
          "50%": { opacity: "1" },
        },
        popIn: {
          "0%": { opacity: "0", transform: "scale(0.9) translateY(6px)" },
          "100%": { opacity: "1", transform: "scale(1) translateY(0)" },
        },
        checkPop: {
          "0%": { transform: "scale(0.6)" },
          "60%": { transform: "scale(1.15)" },
          "100%": { transform: "scale(1)" },
        },
        countUp: {
          "0%": { opacity: "0", transform: "translateY(4px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
      },
    },
  },
  plugins: [],
};
