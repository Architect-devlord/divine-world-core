/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}",
    "./src/components/**/*.{js,jsx,ts,tsx}"
  ],
  theme: {
    extend: {
      colors: {
        'scrollbar': 'hsl(var(--bc) / 0.2)',
        'scrollbar-hover': 'hsl(var(--bc) / 0.3)',
      },
    },
  },
  plugins: [require("daisyui")],
  daisyui: {
    themes: ["light", "dark", "corporate"],
    darkTheme: "dark",
    base: true,
    styled: true,
    utils: true,
    logs: false,
  },
  important: true,
}