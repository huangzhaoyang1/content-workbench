import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        background: "var(--background)",
        foreground: "var(--foreground)",
        border: "var(--border)",
        input: "var(--input)",
        ring: "var(--ring)",
        card: {
          DEFAULT: "var(--card)",
          foreground: "var(--card-foreground)",
        },
        popover: {
          DEFAULT: "var(--popover)",
          foreground: "var(--popover-foreground)",
        },
        primary: {
          DEFAULT: "var(--primary)",
          foreground: "var(--primary-foreground)",
        },
        secondary: {
          DEFAULT: "var(--secondary)",
          foreground: "var(--secondary-foreground)",
        },
        muted: {
          DEFAULT: "var(--muted)",
          foreground: "var(--muted-foreground)",
        },
        /** 品牌琥珀金：当前步骤高亮 / 关键动作 / 警示，克制使用 */
        accent: "#C8A96A",
        destructive: {
          DEFAULT: "var(--destructive)",
          foreground: "var(--destructive-foreground)",
        },
        /** 状态色（三色 toast / 徽标 / 节点状态） */
        success: "#4CAF7D",
        warning: "#C8A96A",
        error: "#C46A5A",
        info: "#6A8FB5",
        chart: {
          "1": "var(--chart-1)",
          "2": "var(--chart-2)",
          "3": "var(--chart-3)",
          "4": "var(--chart-4)",
          "5": "var(--chart-5)",
        },
        sidebar: {
          DEFAULT: "var(--sidebar)",
          foreground: "var(--sidebar-foreground)",
          primary: "var(--sidebar-primary)",
          "primary-foreground": "var(--sidebar-primary-foreground)",
          accent: "var(--sidebar-accent)",
          "accent-foreground": "var(--sidebar-accent-foreground)",
          border: "var(--sidebar-border)",
          ring: "var(--sidebar-ring)",
        },
        /** 品牌表面令牌 */
        base: "#0B0F17",
        surface: "#131A26",
        elevated: "#1A2233",
        subtle: "#243044",
        "primary-2": "#2D5A8E",
        /** 文字层级：ink=主 / ink-2=次 / ink-3=弱 */
        ink: "#E8ECF3",
        "ink-2": "#9AA5B5",
        "ink-3": "#5B6675",
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
      keyframes: {
        "toast-in": {
          from: { opacity: "0", transform: "translateX(12px) scale(0.98)" },
          to: { opacity: "1", transform: "translateX(0) scale(1)" },
        },
        "fade-in": {
          from: { opacity: "0", transform: "translateY(4px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          from: { opacity: "0", transform: "translateY(8px) scale(0.97)" },
          to: { opacity: "1", transform: "translateY(0) scale(1)" },
        },
        "overlay-in": {
          from: { opacity: "0" },
          to: { opacity: "1" },
        },
        "slide-in-left": {
          from: { opacity: "0", transform: "translateX(-100%)" },
          to: { opacity: "1", transform: "translateX(0)" },
        },
        "indeterminate": {
          "0%": { transform: "translateX(-100%)" },
          "100%": { transform: "translateX(340%)" },
        },
        /** 运行中节点：琥珀金流光（移动渐变背景） */
        flow: {
          "0%": { backgroundPosition: "0% 50%" },
          "100%": { backgroundPosition: "200% 50%" },
        },
        /** 全部完成：绿色呼吸一次，提示成功 */
        breathe: {
          "0%,100%": {
            boxShadow: "0 0 0 0 rgba(76,175,125,0)",
            borderColor: "rgba(76,175,125,0.4)",
          },
          "50%": {
            boxShadow: "0 0 0 6px rgba(76,175,125,0.18)",
            borderColor: "rgba(76,175,125,0.9)",
          },
        },
        /** 页面切换淡入 150ms */
        "page-in": {
          from: { opacity: "0", transform: "translateY(6px)" },
          to: { opacity: "1", transform: "translateY(0)" },
        },
        /** 当前步骤：琥珀金柔光 */
        glow: {
          "0%,100%": { boxShadow: "0 0 0 0 rgba(200,169,106,0)" },
          "50%": { boxShadow: "0 0 0 4px rgba(200,169,106,0.22)" },
        },
      },
      animation: {
        "toast-in": "toast-in 0.2s ease-out",
        "fade-in": "fade-in 0.28s ease-out both",
        "scale-in": "scale-in 0.18s ease-out",
        "overlay-in": "overlay-in 0.18s ease-out",
        "slide-in-left": "slide-in-left 0.22s ease-out",
        indeterminate: "indeterminate 1.2s ease-in-out infinite",
        flow: "flow 1.4s linear infinite",
        breathe: "breathe 1.8s ease-in-out",
        "page-in": "page-in 0.15s ease-out both",
        glow: "glow 2s ease-in-out infinite",
      },
    },
  },
  plugins: [],
};
export default config;
