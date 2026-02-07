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
        brand: {
          primary: '#6366f1', // Indigo 500
          secondary: '#06b6d4', // Cyan 500
          accent: '#f43f5e', // Rose 500
          dark: '#0f172a', // Slate 900
          light: '#f8fafc', // Slate 50
        }
      },
    },
  },
  plugins: [require("daisyui")],
  daisyui: {
    themes: [
      {
        dark: {
          "primary": "#6366f1",
          "secondary": "#06b6d4",
          "accent": "#f43f5e",
          "neutral": "#1e293b",
          "base-100": "#0f172a",
          "info": "#3abff8",
          "success": "#36d399",
          "warning": "#fbbd23",
          "error": "#f87272",
        },
      },
      "light",
    ],
    darkTheme: "dark",
    base: true,
    styled: true,
    utils: true,
    logs: false,
  },
  important: true,
}
