"use client";

// Light/dark theming and user defaults, persisted in localStorage.
// The document attribute itself is set before paint by THEME_BOOTSTRAP_SCRIPT;
// the store below keeps every subscribed component in sync afterwards, so the
// header toggle and the Settings panel never disagree.

import { useCallback, useSyncExternalStore } from "react";
import { THEME_STORAGE_KEY } from "./theme-script";
import type { DepthLevel } from "./types";

export type ThemeMode = "system" | "light" | "dark";
export type ResolvedTheme = "light" | "dark";

const DEPTH_STORAGE_KEY = "jev-default-depth";
const DARK_QUERY = "(prefers-color-scheme: dark)";

export const DEFAULT_DEPTH: DepthLevel = "standard";

function prefersDark(): boolean {
  return (
    typeof window !== "undefined" && window.matchMedia(DARK_QUERY).matches
  );
}

export function resolveTheme(mode: ThemeMode): ResolvedTheme {
  if (mode === "system") return prefersDark() ? "dark" : "light";
  return mode;
}

function readStoredTheme(): ThemeMode {
  if (typeof window === "undefined") return "system";
  try {
    const stored = window.localStorage.getItem(THEME_STORAGE_KEY);
    if (stored === "light" || stored === "dark" || stored === "system") {
      return stored;
    }
  } catch {
    // Storage can be blocked (private mode); fall back to the OS preference.
  }
  return "system";
}

function paint(resolved: ResolvedTheme): void {
  if (typeof document === "undefined") return;
  document.documentElement.setAttribute("data-theme", resolved);
  document.documentElement.style.colorScheme = resolved;
}

// ─── Theme store ─────────────────────────────────────────────────────────────
export interface ThemeSnapshot {
  mode: ThemeMode;
  resolved: ResolvedTheme;
}

const SERVER_SNAPSHOT: ThemeSnapshot = { mode: "system", resolved: "light" };
let themeSnapshot: ThemeSnapshot | null = null;
const themeListeners = new Set<() => void>();
let mediaListenerAttached = false;

function getThemeSnapshot(): ThemeSnapshot {
  if (typeof window === "undefined") return SERVER_SNAPSHOT;
  if (!themeSnapshot) {
    const mode = readStoredTheme();
    themeSnapshot = { mode, resolved: resolveTheme(mode) };
  }
  return themeSnapshot;
}

function getServerThemeSnapshot(): ThemeSnapshot {
  return SERVER_SNAPSHOT;
}

function emitTheme(): void {
  themeListeners.forEach((listener) => listener());
}

function onSystemThemeChange(): void {
  if (getThemeSnapshot().mode !== "system") return;
  themeSnapshot = { mode: "system", resolved: resolveTheme("system") };
  paint(themeSnapshot.resolved);
  emitTheme();
}

function onStorageChange(event: StorageEvent): void {
  if (event.key !== THEME_STORAGE_KEY) return;
  themeSnapshot = null;
  const next = getThemeSnapshot();
  paint(next.resolved);
  emitTheme();
}

function subscribeTheme(listener: () => void): () => void {
  themeListeners.add(listener);
  if (!mediaListenerAttached && typeof window !== "undefined") {
    window
      .matchMedia(DARK_QUERY)
      .addEventListener("change", onSystemThemeChange);
    window.addEventListener("storage", onStorageChange);
    mediaListenerAttached = true;
  }
  return () => {
    themeListeners.delete(listener);
  };
}

export function setThemeMode(mode: ThemeMode): void {
  themeSnapshot = { mode, resolved: resolveTheme(mode) };
  paint(themeSnapshot.resolved);
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, mode);
  } catch {
    // Non-fatal: the choice simply will not survive a reload.
  }
  emitTheme();
}

export interface UseThemeReturn extends ThemeSnapshot {
  setMode: (mode: ThemeMode) => void;
}

export function useTheme(): UseThemeReturn {
  const snapshot = useSyncExternalStore(
    subscribeTheme,
    getThemeSnapshot,
    getServerThemeSnapshot
  );
  return { ...snapshot, setMode: setThemeMode };
}

// ─── Default research depth ──────────────────────────────────────────────────
let depthValue: DepthLevel | null = null;
const depthListeners = new Set<() => void>();

function readStoredDepth(): DepthLevel {
  if (typeof window === "undefined") return DEFAULT_DEPTH;
  try {
    const stored = window.localStorage.getItem(DEPTH_STORAGE_KEY);
    if (stored === "shallow" || stored === "standard" || stored === "deep") {
      return stored;
    }
  } catch {
    // Keep the default when storage is unavailable.
  }
  return DEFAULT_DEPTH;
}

function getDepthSnapshot(): DepthLevel {
  if (depthValue === null) depthValue = readStoredDepth();
  return depthValue;
}

function subscribeDepth(listener: () => void): () => void {
  depthListeners.add(listener);
  return () => {
    depthListeners.delete(listener);
  };
}

export function setDefaultDepth(depth: DepthLevel): void {
  depthValue = depth;
  try {
    window.localStorage.setItem(DEPTH_STORAGE_KEY, depth);
  } catch {
    // Non-fatal: the choice simply will not survive a reload.
  }
  depthListeners.forEach((listener) => listener());
}

export interface UseDefaultDepthReturn {
  depth: DepthLevel;
  setDepth: (depth: DepthLevel) => void;
}

export function useDefaultDepth(): UseDefaultDepthReturn {
  const depth = useSyncExternalStore(
    subscribeDepth,
    getDepthSnapshot,
    () => DEFAULT_DEPTH
  );
  const setDepth = useCallback((next: DepthLevel) => setDefaultDepth(next), []);
  return { depth, setDepth };
}
