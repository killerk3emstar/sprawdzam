/**
 * Persists the app settings JSON (owned by JS, see app/src/settings.ts).
 * - The device token is a long-lived secret: it goes to Asset Store Kit (encrypted, device-bound) and is
 *   stripped from the JSON kept in Preferences. If Asset Store is unavailable it falls back to Preferences.
 * - Everything else (language, backend URL, trusted person, flags) goes to Preferences.
 * Whitelist numbers are never stored here; they are read from Contacts when needed.
 */
import { preferences } from '@kit.ArkData';
import { asset } from '@kit.AssetStoreKit';
import { common } from '@kit.AbilityKit';
import { util } from '@kit.ArkTS';
import { hilog } from '@kit.PerformanceAnalysisKit';

const DOMAIN: number = 0x5350;
const TAG: string = 'CallEngine';
const PREFS_NAME: string = 'sprawdzam_settings';
const KEY_SETTINGS: string = 'settings';
const KEY_TOKEN_FALLBACK: string = 'deviceTokenFallback';
const TOKEN_ALIAS: string = 'pl.sprawdzam.app.deviceToken';
const TOKEN_FIELD: string = 'deviceToken';

function toBytes(text: string): Uint8Array {
  return new util.TextEncoder().encodeInto(text);
}

function fromBytes(bytes: Uint8Array): string {
  return util.TextDecoder.create('utf-8').decodeToString(bytes);
}

export class SettingsStore {
  private prefs: preferences.Preferences;

  constructor(context: common.Context) {
    this.prefs = preferences.getPreferencesSync(context, { name: PREFS_NAME });
  }

  /** Returns the stored settings JSON (with the device token merged back), or "{}". */
  load(): string {
    const json = this.prefs.getSync(KEY_SETTINGS, '{}') as string;
    let record: Record<string, Object> = {};
    try {
      record = JSON.parse(json) as Record<string, Object>;
    } catch (e) {
      hilog.warn(DOMAIN, TAG, 'settings: stored JSON is invalid, using defaults');
    }
    const token = this.readToken();
    if (token !== '') {
      record[TOKEN_FIELD] = token;
    }
    return JSON.stringify(record);
  }

  async save(json: string): Promise<void> {
    const parsed = JSON.parse(json) as Record<string, Object>;
    const kept: Record<string, Object> = {};
    for (const key of Object.keys(parsed)) {
      if (key !== TOKEN_FIELD) {
        kept[key] = parsed[key];
      }
    }
    const token = parsed[TOKEN_FIELD];
    if (token !== undefined && token !== null) {
      this.writeToken(String(token));
    }
    this.prefs.putSync(KEY_SETTINGS, JSON.stringify(kept));
    await this.prefs.flush();
  }

  /** Reads one top-level string field (e.g. "lang") from the stored settings. */
  getString(field: string, fallback: string): string {
    try {
      const record = JSON.parse(this.prefs.getSync(KEY_SETTINGS, '{}') as string) as Record<string, Object>;
      const value = record[field];
      return value === undefined || value === null ? fallback : String(value);
    } catch (e) {
      return fallback;
    }
  }

  private readToken(): string {
    try {
      const query: asset.AssetMap = new Map();
      query.set(asset.Tag.ALIAS, toBytes(TOKEN_ALIAS));
      query.set(asset.Tag.RETURN_TYPE, asset.ReturnType.ALL);
      const results = asset.querySync(query);
      if (results.length > 0) {
        const secret = results[0].get(asset.Tag.SECRET) as Uint8Array;
        return fromBytes(secret);
      }
    } catch (e) {
      const code = (e as Record<string, Object>)['code'];
      if (code !== asset.ErrorCode.NOT_FOUND) {
        hilog.warn(DOMAIN, TAG, 'settings: asset query failed (%{public}s), using fallback', String(code));
      }
    }
    return this.prefs.getSync(KEY_TOKEN_FALLBACK, '') as string;
  }

  private writeToken(token: string): void {
    try {
      const query: asset.AssetMap = new Map();
      query.set(asset.Tag.ALIAS, toBytes(TOKEN_ALIAS));
      try {
        asset.removeSync(query);
      } catch (e) {
        // NOT_FOUND on first save is expected.
      }
      if (token === '') {
        return;
      }
      const attrs: asset.AssetMap = new Map();
      attrs.set(asset.Tag.ALIAS, toBytes(TOKEN_ALIAS));
      attrs.set(asset.Tag.SECRET, toBytes(token));
      attrs.set(asset.Tag.ACCESSIBILITY, asset.Accessibility.DEVICE_FIRST_UNLOCKED);
      asset.addSync(attrs);
      this.prefs.deleteSync(KEY_TOKEN_FALLBACK);
      hilog.info(DOMAIN, TAG, 'settings: device token stored in Asset Store');
    } catch (e) {
      const code = (e as Record<string, Object>)['code'];
      hilog.warn(DOMAIN, TAG, 'settings: asset store unavailable (%{public}s), keeping token in preferences',
        String(code));
      this.prefs.putSync(KEY_TOKEN_FALLBACK, token);
    }
  }
}
