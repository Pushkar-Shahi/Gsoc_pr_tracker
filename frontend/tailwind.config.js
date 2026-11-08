/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0fdf4',
          100: '#dcfce7',
          500: '#22c55e',
          600: '#16a34a',
          700: '#15803d',
        },
        dark: {
          bg: '#000000',
          card: '#0a0a0a',
          surface: '#050505',
          border: '#1f1f1f',
          hover: '#141414',
        },
        amoled: {
          bg: '#000000',
          card: '#080808',
          elevated: '#0f0f0f',
          border: '#1f1f1f',
          borderLight: 'rgba(255, 255, 255, 0.12)',
          text: '#FFFFFF',
          textMuted: '#A1A1AA',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
      keyframes: {
        'scanner-beam': {
          '0%': { transform: 'translateY(-100%)', opacity: '0.2' },
          '50%': { opacity: '0.9' },
          '100%': { transform: 'translateY(100%)', opacity: '0.2' },
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translate3d(0, 8px, 0)' },
          '100%': { opacity: '1', transform: 'translate3d(0, 0, 0)' },
        },
        'scale-up': {
          '0%': { opacity: '0', transform: 'scale(0.97)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'slide-left': {
          '0%': { transform: 'translate3d(100%, 0, 0)' },
          '100%': { transform: 'translate3d(0, 0, 0)' },
        },
        'slide-right': {
          '0%': { transform: 'translate3d(-100%, 0, 0)' },
          '100%': { transform: 'translate3d(0, 0, 0)' },
        },
        'slide-up': {
          '0%': { opacity: '0', transform: 'translate3d(0, 16px, 0)' },
          '100%': { opacity: '1', transform: 'translate3d(0, 0, 0)' },
        },
        'dropdown': {
          '0%': { opacity: '0', transform: 'translate3d(0, -6px, 0) scale(0.98)' },
          '100%': { opacity: '1', transform: 'translate3d(0, 0, 0) scale(1)' },
        },
        'monochrome-glow': {
          '0%, 100%': { boxShadow: '0 0 15px rgba(255, 255, 255, 0.08)' },
          '50%': { boxShadow: '0 0 30px rgba(255, 255, 255, 0.18)' },
        }
      },
      animation: {
        'scanner': 'scanner-beam 2s ease-in-out infinite',
        'fade-in': 'fade-in 0.15s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'fade-in-up': 'fade-in-up 0.2s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'scale-up': 'scale-up 0.18s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'slide-left': 'slide-left 0.22s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'slide-right': 'slide-right 0.22s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'slide-up': 'slide-up 0.2s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'dropdown': 'dropdown 0.14s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'monochrome-glow': 'monochrome-glow 3s ease-in-out infinite',
      }
    },
  },
  plugins: [],
}
