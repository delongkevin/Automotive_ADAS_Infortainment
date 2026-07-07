import Constants from 'expo-constants';

const DEFAULT_ANDROID_EMULATOR = 'http://10.0.2.2:8000';

export function getApiBaseUrl() {
  const configured = Constants?.expoConfig?.extra?.apiBaseUrl;
  if (configured && typeof configured === 'string') {
    return configured.replace(/\/$/, '');
  }
  return DEFAULT_ANDROID_EMULATOR;
}
