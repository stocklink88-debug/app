/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: { 900: '#080B11', 800: '#0D111A', 700: '#141A26', 600: '#1C2432', 500: '#2A3444' },
        accent: { DEFAULT: '#FFD24A', soft: '#FFE9A3', deep: '#E0A800' },
        mint: '#3DDC97',
        coral: '#FF6B6B',
      },
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
      animation: { 'pulse-soft': 'pulse 2.4s cubic-bezier(0.4,0,0.6,1) infinite' },
    },
  },
  plugins: [],
}
