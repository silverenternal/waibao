"use client";

import * as React from "react";
import { ThemeProvider as NextThemesProvider } from "next-themes";

/**
 * ThemeProvider — accessibility-focused theme switcher.
 *
 * Supports:
 *   - light / dark / system color schemes
 *   - high-contrast mode (WCAG 2.1 AAA-equivalent contrast)
 *   - large-text mode (text size: lg, xl)
 *   - reduced-motion mode (forces prefers-reduced-motion)
 *
 * Persists preferences to localStorage and exposes a settings hook.
 */

export type ColorScheme = "light" | "dark" | "system";
export type ContrastMode = "normal" | "hc" | "hc-light";
export type TextSize = "normal" | "lg" | "xl";

export interface A11yPreferences {
  colorScheme: ColorScheme;
  contrast: ContrastMode;
  textSize: TextSize;
  reducedMotion: boolean;
}

const STORAGE_KEY = "waibao.a11y.v1";
const DEFAULT_PREFERENCES: A11yPreferences = {
  colorScheme: "system",
  contrast: "normal",
  textSize: "normal",
  reducedMotion: false,
};

function readStorage(): A11yPreferences {
  if (typeof window === "undefined") return DEFAULT_PREFERENCES;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_PREFERENCES;
    return { ...DEFAULT_PREFERENCES, ...JSON.parse(raw) };
  } catch {
    return DEFAULT_PREFERENCES;
  }
}

function writeStorage(prefs: A11yPreferences) {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs));
  } catch {
    /* ignore quota errors */
  }
}

function applyToDocument(prefs: A11yPreferences) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;

  // Color scheme
  if (prefs.colorScheme === "dark") {
    root.classList.add("dark");
    root.style.colorScheme = "dark";
  } else if (prefs.colorScheme === "light") {
    root.classList.remove("dark");
    root.style.colorScheme = "light";
  } else {
    root.style.colorScheme = "light dark";
  }

  // Contrast
  root.removeAttribute("data-theme");
  if (prefs.contrast !== "normal") {
    root.setAttribute("data-theme", prefs.contrast);
  }

  // Text size
  if (prefs.textSize === "normal") {
    root.removeAttribute("data-text-size");
  } else {
    root.setAttribute("data-text-size", prefs.textSize);
  }

  // Reduced motion
  if (prefs.reducedMotion) {
    root.setAttribute("data-reduced-motion", "true");
  } else {
    root.removeAttribute("data-reduced-motion");
  }
}

export interface ThemeContextValue {
  preferences: A11yPreferences;
  setPreference: <K extends keyof A11yPreferences>(
    key: K,
    value: A11yPreferences[K]
  ) => void;
  reset: () => void;
}

const ThemeContext = React.createContext<ThemeContextValue | null>(null);

export interface ThemeProviderProps {
  children: React.ReactNode;
  /** Default preferences, merged with stored values. */
  defaultPreferences?: Partial<A11yPreferences>;
}

export function ThemeProvider({
  children,
  defaultPreferences,
}: ThemeProviderProps) {
  const [preferences, setPreferences] =
    React.useState<A11yPreferences>(DEFAULT_PREFERENCES);

  // Hydrate from localStorage on mount
  React.useEffect(() => {
    const stored = readStorage();
    const merged = { ...stored, ...(defaultPreferences || {}) };
    setPreferences(merged);
    applyToDocument(merged);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const setPreference = React.useCallback(
    <K extends keyof A11yPreferences>(key: K, value: A11yPreferences[K]) => {
      setPreferences((prev) => {
        const next = { ...prev, [key]: value };
        writeStorage(next);
        applyToDocument(next);
        return next;
      });
    },
    []
  );

  const reset = React.useCallback(() => {
    const next = { ...DEFAULT_PREFERENCES, ...(defaultPreferences || {}) };
    setPreferences(next);
    writeStorage(next);
    applyToDocument(next);
  }, [defaultPreferences]);

  const value = React.useMemo<ThemeContextValue>(
    () => ({ preferences, setPreference, reset }),
    [preferences, setPreference, reset]
  );

  return (
    <NextThemesProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
      <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>
    </NextThemesProvider>
  );
}

export function useA11yPreferences() {
  const ctx = React.useContext(ThemeContext);
  if (!ctx) {
    throw new Error("useA11yPreferences must be used inside <ThemeProvider>");
  }
  return ctx;
}

/** A small UI panel component for toggling a11y preferences. */
export function A11ySettingsPanel() {
  const { preferences, setPreference } = useA11yPreferences();
  return (
    <div
      role="region"
      aria-label="Accessibility settings"
      className="flex flex-col gap-3 text-sm"
    >
      <fieldset className="flex flex-col gap-2">
        <legend className="font-medium">Color scheme</legend>
        {(["light", "dark", "system"] as ColorScheme[]).map((scheme) => (
          <label key={scheme} className="flex items-center gap-2">
            <input
              type="radio"
              name="color-scheme"
              value={scheme}
              checked={preferences.colorScheme === scheme}
              onChange={() => setPreference("colorScheme", scheme)}
            />
            <span className="capitalize">{scheme}</span>
          </label>
        ))}
      </fieldset>
      <fieldset className="flex flex-col gap-2">
        <legend className="font-medium">Contrast</legend>
        {[
          { value: "normal", label: "Normal" },
          { value: "hc", label: "High contrast (dark)" },
          { value: "hc-light", label: "High contrast (light)" },
        ].map((opt) => (
          <label key={opt.value} className="flex items-center gap-2">
            <input
              type="radio"
              name="contrast"
              value={opt.value}
              checked={preferences.contrast === opt.value}
              onChange={() =>
                setPreference("contrast", opt.value as ContrastMode)
              }
            />
            <span>{opt.label}</span>
          </label>
        ))}
      </fieldset>
      <fieldset className="flex flex-col gap-2">
        <legend className="font-medium">Text size</legend>
        {[
          { value: "normal", label: "Normal" },
          { value: "lg", label: "Large" },
          { value: "xl", label: "Extra large" },
        ].map((opt) => (
          <label key={opt.value} className="flex items-center gap-2">
            <input
              type="radio"
              name="text-size"
              value={opt.value}
              checked={preferences.textSize === opt.value}
              onChange={() =>
                setPreference("textSize", opt.value as TextSize)
              }
            />
            <span>{opt.label}</span>
          </label>
        ))}
      </fieldset>
      <label className="flex items-center gap-2">
        <input
          type="checkbox"
          checked={preferences.reducedMotion}
          onChange={(e) => setPreference("reducedMotion", e.target.checked)}
        />
        <span>Reduce motion</span>
      </label>
    </div>
  );
}

export default ThemeProvider;
