/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      // Self-hosted Outfit (see @font-face in index.css), with a native
      // system-font fallback while the woff2 loads / if it's unavailable.
      fontFamily: {
        sans: [
          "Outfit",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
      },
      colors: {
        brand: {
          DEFAULT: "#0f172a",
          accent: "#2563eb",
        },
      },
    },
  },
  plugins: [],
};
