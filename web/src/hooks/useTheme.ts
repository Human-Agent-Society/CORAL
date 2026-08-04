import { useSyncExternalStore } from "react";

export type Theme = "light" | "dark";
export type ThemePreference = Theme | "system";

interface ThemeState {
  theme: Theme;
  preference: ThemePreference;
}

export const THEME_STORAGE_KEY = "coral-theme";

const listeners = new Set<() => void>();
const serverState: ThemeState = { theme: "light", preference: "system" };
let currentState: ThemeState | null = null;
let systemListenerAttached = false;

function storedPreference(): ThemePreference {
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") return stored;
  } catch {
    // Storage can be unavailable in privacy-restricted browser contexts.
  }

  return "system";
}

function systemTheme(): Theme {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function resolveTheme(preference: ThemePreference): Theme {
  return preference === "system" ? systemTheme() : preference;
}

function applyTheme(state: ThemeState) {
  const root = document.documentElement;
  root.classList.toggle("dark", state.theme === "dark");
  root.dataset.theme = state.theme;
  root.dataset.themePreference = state.preference;
  root.style.colorScheme = state.theme;
}

function updateState(preference: ThemePreference, notify: boolean) {
  const nextState = { theme: resolveTheme(preference), preference };
  if (
    currentState?.theme === nextState.theme &&
    currentState.preference === nextState.preference
  ) {
    return;
  }

  currentState = nextState;
  applyTheme(nextState);
  if (notify) listeners.forEach((listener) => listener());
}

function attachSystemListener() {
  if (systemListenerAttached) return;
  systemListenerAttached = true;
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => {
    if (currentState?.preference === "system") updateState("system", true);
  });
}

export function initializeTheme(): ThemeState {
  updateState(storedPreference(), false);
  attachSystemListener();
  return currentState ?? serverState;
}

export function setThemePreference(preference: ThemePreference) {
  updateState(preference, true);
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, preference);
  } catch {
    // The theme still applies for the current session when storage is blocked.
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot(): ThemeState {
  return currentState ?? initializeTheme();
}

export function useTheme() {
  const state = useSyncExternalStore(subscribe, getSnapshot, () => serverState);
  return { ...state, setPreference: setThemePreference };
}
