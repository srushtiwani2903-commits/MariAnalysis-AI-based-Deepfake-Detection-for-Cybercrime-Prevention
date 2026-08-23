/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#050816",
          900: "#0a0e27",
          800: "#101639",
          700: "#1a2150",
        },
        neon: {
          // Accent follows the theme: neon blue/cyan in dark mode,
          // cyber dark-green in light mode (see --accent vars in index.css).
          blue: "rgb(var(--accent) / <alpha-value>)",
          cyan: "rgb(var(--accent-2) / <alpha-value>)",
          purple: "#7c3aed",
          pink: "#e879f9",
        },
      },
      fontFamily: {
        sans: ["Inter", "Segoe UI", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "Consolas", "monospace"],
      },
      boxShadow: {
        glow: "0 0 20px rgba(34, 211, 238, 0.35)",
        "glow-purple": "0 0 25px rgba(124, 58, 237, 0.45)",
        glass: "0 8px 32px 0 rgba(0, 0, 0, 0.35)",
      },
      backgroundImage: {
        "grid-pattern": "linear-gradient(rgba(34,211,238,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(34,211,238,0.05) 1px, transparent 1px)",
      },
      animation: {
        "scan-line": "scanline 2.5s ease-in-out infinite",
        float: "float 6s ease-in-out infinite",
        "pulse-slow": "pulse 4s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        "spin-slow": "spin 8s linear infinite",
        shimmer: "shimmer 2.5s linear infinite",
      },
      keyframes: {
        scanline: {
          "0%, 100%": { top: "0%" },
          "50%": { top: "100%" },
        },
        float: {
          "0%, 100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-12px)" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
      },
    },
  },
  plugins: [],
};
