/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}',
  ],
  theme: {
    extend: {
      colors: {
        'cosmic-bg': '#0b0b1e',
        'cosmic-purple': '#4c1d95',
        'cosmic-gold': '#fbbf24',
      },
      keyframes: {
        twinkle: {
          '0%, 100%': { opacity: '1', transform: 'scale(1)' },
          '50%': { opacity: '0.3', transform: 'scale(0.8)' },
        },
        'pulse-glow': {
          '0%': { boxShadow: '0 0 5px #fbbf24' },
          '50%': { boxShadow: '0 0 20px #fbbf24, 0 0 40px #4c1d95' },
          '100%': { boxShadow: '0 0 5px #fbbf24' },
        },
        'milky-way': {
          '0%, 100%': { opacity: '0.04' },
          '50%': { opacity: '0.1' },
        },
        'sky-scroll': {
          '0%': { transform: 'translateX(12%) rotate(0deg)' },
          '50%': { transform: 'translateX(-12%) rotate(-6deg)' },
          '100%': { transform: 'translateX(12%) rotate(0deg)' },
        },
        'plus-pulse': {
          '0%, 100%': { transform: 'scale(1)' },
          '50%': { transform: 'scale(1.15)' },
        },
        'plus-spin': {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(180deg)' },
        },
        float: {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-1.8px)' },
        },
        'float-alt': {
          '0%, 100%': { transform: 'translateY(0)' },
          '33%': { transform: 'translateY(-2.2px)' },
          '66%': { transform: 'translateY(1.2px)' },
        },
        'float-slow': {
          '0%, 100%': { transform: 'translateY(0.2px)' },
          '50%': { transform: 'translateY(-1.5px)' },
        },
        'moon-levitate': {
          '0%, 100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-2px)' },
        },
      },
      boxShadow: {
        'gold': '0 0 24px rgba(251, 191, 36, 0.4)',
        'gold-lg': '0 0 32px rgba(251, 191, 36, 0.5)',
      },
      animation: {
        'plus-pulse': 'plus-pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'plus-spin': 'plus-spin 4s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        twinkle: 'twinkle 3s ease-in-out infinite',
        'twinkle-slow': 'twinkle 6s ease-in-out infinite',
        'twinkle-fast': 'twinkle 1.5s ease-in-out infinite',
        'pulse-glow': 'pulse-glow 3s infinite',
        'milky-way': 'milky-way 8s ease-in-out infinite',
        'sky-scroll': 'sky-scroll 45s linear infinite',
        float: 'float 5s ease-in-out infinite',
        'float-alt': 'float-alt 6s ease-in-out infinite',
        'float-slow': 'float-slow 7s ease-in-out infinite',
        'moon-levitate': 'moon-levitate 7s ease-in-out infinite',
      },
    },
  },
  plugins: [],
};
