import { usePreferencesContext } from '../contexts/PreferencesContext';

export function usePreferences() {
  const { preferences, updatePreferences } = usePreferencesContext();

  return { preferences, update: updatePreferences };
}
