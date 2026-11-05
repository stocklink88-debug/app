/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          950: '#050507',
          900: '#0A0A0D',
          800: '#101014',
          700: '#17171D',
          600: '#1F1F27',
          500: '#2A2A34',
          400: '#3A3A46',
        },
        brand: { DEFAULT: '#C8FF4D', soft: '#E2FF9B', deep: '#A2D62C' },
        flame: '#FF5C38',
        iris: '#7C6BFF',
        aqua: '#36E0C8',
      },
      fontFamily: { sans: ['Inter', 'system-ui', 'sans-serif'] },
      keyframes: {
        rise: { from: { opacity: '0', transform: 'translateY(8px)' }, to: { opacity: '1', transform: 'none' } },
        shimmer: { '100%': { transform: 'translateX(100%)' } },
      },
      animation: { rise: 'rise .35s ease-out both', shimmer: 'shimmer 1.6s infinite' },
    },
  },
  plugins: [],
}
