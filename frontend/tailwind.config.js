/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        base: {
          950: "#070a0f",
          900: "#0b1017",
          850: "#0f1620",
          800: "#141d29",
          700: "#1d2836",
          600: "#2a3849",
        },
        accent: "#38bdf8",
      },
      fontFamily: {
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Consolas", "monospace"],
      },
      boxShadow: {
        glow: "0 0 0 1px rgba(56,189,248,0.35), 0 0 18px rgba(56,189,248,0.18)",
      },
    },
  },
  plugins: [],
};
