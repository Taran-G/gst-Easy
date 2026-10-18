import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "#FAFAF9",
        surface: "#FFFFFF",
        border: "#E7E5E4",
        ink: "#1C1917",
        muted: "#78716C",
        primary: {
          DEFAULT: "#1E3A5F",
          hover: "#152843",
          light: "#EBF1F6"
        },
        success: {
          DEFAULT: "#2F7D5B",
          light: "#EAF5EE"
        },
        warning: {
          DEFAULT: "#B7791F",
          light: "#FEF7EC"
        },
        danger: {
          DEFAULT: "#B4443C",
          light: "#FDF2F2"
        }
      },
      fontFamily: {
        sans: ["Inter", "-apple-system", "BlinkMacSystemFont", "Segoe UI", "sans-serif"],
      }
    },
  },
  plugins: [],
};
export default config;
