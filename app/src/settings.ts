/**
 * App settings, persisted natively (Preferences; the device token in Asset Store Kit on HarmonyOS).
 * Falls back to in-memory defaults where the native module is missing (Android stub, tests).
 */
import {CallEngine, isCallEngineAvailable} from './native/CallEngine';
import type {Lang} from './i18n';

export type TrustedPerson = {name: string; number: string};

export type Settings = {
  lang: Lang;
  controlUrl: string;
  deviceToken: string;
  trustedPerson: TrustedPerson | null;
  notificationsAsked: boolean;
};

// Dev defaults: fake/dev backend through `hdc rport tcp:8765 tcp:8765`. Production uses wss://.
export const DEFAULT_SETTINGS: Settings = {
  lang: 'pl',
  controlUrl: 'ws://127.0.0.1:8765/app/control',
  deviceToken: 'dev-device-1',
  trustedPerson: null,
  notificationsAsked: false,
};

export function parseSettings(json: string): Settings {
  let raw: Partial<Settings> = {};
  try {
    raw = JSON.parse(json) as Partial<Settings>;
  } catch {
    raw = {};
  }
  const tp = raw.trustedPerson;
  return {
    lang: raw.lang === 'en' ? 'en' : raw.lang === 'pl' ? 'pl' : DEFAULT_SETTINGS.lang,
    controlUrl: typeof raw.controlUrl === 'string' && raw.controlUrl ? raw.controlUrl : DEFAULT_SETTINGS.controlUrl,
    deviceToken:
      typeof raw.deviceToken === 'string' && raw.deviceToken ? raw.deviceToken : DEFAULT_SETTINGS.deviceToken,
    trustedPerson:
      tp && typeof tp.name === 'string' && typeof tp.number === 'string' ? {name: tp.name, number: tp.number} : null,
    notificationsAsked: raw.notificationsAsked === true,
  };
}

export async function loadSettings(): Promise<Settings> {
  if (!isCallEngineAvailable()) {
    return DEFAULT_SETTINGS;
  }
  try {
    return parseSettings(await CallEngine.loadSettings());
  } catch {
    return DEFAULT_SETTINGS;
  }
}

export async function saveSettings(settings: Settings): Promise<void> {
  if (!isCallEngineAvailable()) {
    return;
  }
  try {
    await CallEngine.saveSettings(JSON.stringify(settings));
  } catch {
    // Not persisted (e.g. Android stub); the in-memory settings still apply.
  }
}
