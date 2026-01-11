import { usePreferencesContext } from '../contexts/PreferencesContext';
import type { Theme } from '../types';

export function useTheme(): Theme {
  const { theme } = usePreferencesContext();
  return theme;
}