export const tokens = {
  color: { brand: { 50: "#ecfdf8", 500: "#00d4aa", 600: "#00a888", 950: "#042f2b" }, semantic: { success: "#22c55e", warning: "#f59e0b", danger: "#ef4444", info: "#3b82f6" } },
  spacing: { xs: "0.25rem", sm: "0.5rem", md: "1rem", lg: "1.5rem", xl: "2rem", "2xl": "3rem" },
  typography: { fontFamily: { sans: "var(--font-sans)", mono: "var(--font-mono)" }, size: { xs: "0.75rem", sm: "0.875rem", base: "1rem", lg: "1.125rem", xl: "1.25rem", "2xl": "1.5rem", "3xl": "1.875rem" } },
  radius: { sm: "0.5rem", md: "0.75rem", lg: "1rem" },
} as const;
export type DesignTokens = typeof tokens;
