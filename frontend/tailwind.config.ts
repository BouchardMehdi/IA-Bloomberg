import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{js,ts,jsx,tsx,mdx}", "./components/**/*.{js,ts,jsx,tsx,mdx}"],
  theme: {
    extend: {
      colors: {
        ink: "#111827",
        paper: "#f5f7f4",
        signal: "#c8ff61",
      },
    },
  },
  plugins: [],
};

export default config;
