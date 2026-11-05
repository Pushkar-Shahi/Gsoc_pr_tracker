import { useState, useEffect } from 'react';

export type ThemeMode = 'light' | 'dark';

export const THEME_COLORS = {
  dark: {
    bg: '#080c14',
    text: '#f1f5f9'
  },
  light: {
    bg: '#edf2f7',
    text: '#0f172a'
  }
};

export function getInitialTheme(): ThemeMode {
  if (typeof window === 'undefined') return 'dark';
  try {
    const saved = localStorage.getItem('theme');
    if (saved === 'dark' || saved === 'light') return saved;
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  } catch {
    return 'dark';
  }
}

/**
 * Temporarily disables all CSS transitions across the entire DOM during theme toggling.
 * This completely eliminates frame drops and compositor lag caused by interpolating
 * backdrop-filters, box-shadows, and background gradients simultaneously.
 */
export function withDisabledTransitions(fn: () => void) {
  if (typeof document === 'undefined') {
    fn();
    return;
  }

  const css = document.createElement('style');
  css.setAttribute('type', 'text/css');
  css.appendChild(
    document.createTextNode(
      `*, *::before, *::after {
        -webkit-transition: none !important;
        -moz-transition: none !important;
        -o-transition: none !important;
        -ms-transition: none !important;
        transition: none !important;
      }`
    )
  );
  document.head.appendChild(css);

  try {
    fn();
  } finally {
    // Force layout style recalculation so DOM applies changes in 1 frame
    (() => window.getComputedStyle(document.body).opacity)();

    // Remove the transition override on the following animation frame
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        if (css.parentNode) {
          css.parentNode.removeChild(css);
        }
      });
    });
  }
}

export function applyTheme(theme: ThemeMode) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  const isDark = theme === 'dark';

  if (isDark) {
    root.classList.add('dark');
    root.classList.remove('light');
    root.style.colorScheme = 'dark';
    root.style.backgroundColor = THEME_COLORS.dark.bg;
  } else {
    root.classList.remove('dark');
    root.classList.add('light');
    root.style.colorScheme = 'light';
    root.style.backgroundColor = THEME_COLORS.light.bg;
  }

  // Update meta theme-color for iOS/Android status bar
  const metaTheme = document.querySelector('meta[name="theme-color"]');
  if (metaTheme) {
    metaTheme.setAttribute('content', isDark ? THEME_COLORS.dark.bg : THEME_COLORS.light.bg);
  }
}

export function useTheme() {
  const [theme, setThemeState] = useState<ThemeMode>(getInitialTheme);

  useEffect(() => {
    // Initial sync
    applyTheme(theme);

    // Listen to OS system preference changes if user hasn't explicitly set a preference
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = (e: MediaQueryListEvent) => {
      const saved = localStorage.getItem('theme');
      if (!saved) {
        const newTheme: ThemeMode = e.matches ? 'dark' : 'light';
        withDisabledTransitions(() => {
          applyTheme(newTheme);
          setThemeState(newTheme);
        });
      }
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [theme]);

  const toggleTheme = () => {
    const nextTheme: ThemeMode = theme === 'dark' ? 'light' : 'dark';
    try {
      localStorage.setItem('theme', nextTheme);
    } catch {}

    withDisabledTransitions(() => {
      applyTheme(nextTheme);
      setThemeState(nextTheme);
    });
  };

  return { theme, isDark: theme === 'dark', toggleTheme };
}
