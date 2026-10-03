/**
 * Contacts Kit integration without broad permissions: the system contact picker (contact.selectContacts)
 * needs no READ_CONTACTS permission, which on HarmonyOS is a system_basic (ACL-restricted) permission.
 * - Trusted person: single pick, returned to JS for display and settings.
 * - Whitelist: multi pick of the contacts whose calls should ring normally. The numbers stay native
 *   (Preferences in the app sandbox) and are only sent to the backend over the control channel.
 *   They are never logged and never passed to JS (JS only gets the count).
 */
import { contact } from '@kit.ContactsKit';
import { preferences } from '@kit.ArkData';
import { common } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';

const DOMAIN: number = 0x5350;
const TAG: string = 'CallEngine';
const PREFS_NAME: string = 'sprawdzam_contacts';
const KEY_WHITELIST: string = 'whitelist';

export interface PickedContact {
  name: string;
  number: string;
}

/**
 * Normalizes a phone number to E.164-like form for matching on the backend:
 * keeps digits and a leading "+", turns "00" into "+", and treats 9-digit numbers as Polish (+48).
 */
export function normalizeNumber(raw: string): string {
  let n = raw.replace(/[^0-9+]/g, '');
  if (n.startsWith('00')) {
    n = '+' + n.substring(2);
  }
  if (!n.startsWith('+')) {
    n = n.replace(/\+/g, '');
    if (n.length === 9) {
      n = '+48' + n;
    } else if (n.length === 11 && n.startsWith('48')) {
      n = '+' + n;
    }
  }
  return n;
}

function firstNumber(c: contact.Contact): string {
  const numbers = c.phoneNumbers ?? [];
  for (const p of numbers) {
    const normalized = normalizeNumber(p.phoneNumber ?? '');
    if (normalized.length >= 6) {
      return normalized;
    }
  }
  return '';
}

export class ContactsBridge {
  private prefs: preferences.Preferences;

  constructor(context: common.Context) {
    this.prefs = preferences.getPreferencesSync(context, { name: PREFS_NAME });
  }

  /** Opens the system picker for one contact. Resolves null when cancelled or the contact has no number. */
  async pickOne(): Promise<PickedContact | null> {
    const options: contact.ContactSelectionOptions = { isMultiSelect: false };
    const picked = await contact.selectContacts(options);
    if (picked.length === 0) {
      return null;
    }
    const c = picked[0];
    const number = firstNumber(c);
    if (number === '') {
      return null;
    }
    const name = c.name?.fullName ?? number;
    hilog.info(DOMAIN, TAG, 'contacts: trusted person picked');
    const result: PickedContact = { name: name, number: number };
    return result;
  }

  /** Opens the picker in multi-select mode and stores all numbers of the chosen contacts. Returns the count. */
  async pickWhitelist(): Promise<number> {
    const options: contact.ContactSelectionOptions = { isMultiSelect: true };
    let picked: contact.Contact[] = [];
    try {
      picked = await contact.selectContacts(options);
    } catch (e) {
      const err = e as BusinessError;
      hilog.warn(DOMAIN, TAG, 'contacts: picker failed %{public}s', String(err.code));
      throw new Error(`contact picker failed: ${err.code}`);
    }
    if (picked.length === 0) {
      return this.whitelist().length; // cancelled: keep the previous list
    }
    const numbers = new Set<string>();
    for (const c of picked) {
      for (const p of c.phoneNumbers ?? []) {
        const n = normalizeNumber(p.phoneNumber ?? '');
        if (n.length >= 6) {
          numbers.add(n);
        }
      }
    }
    const list = Array.from(numbers);
    this.prefs.putSync(KEY_WHITELIST, JSON.stringify(list));
    await this.prefs.flush();
    hilog.info(DOMAIN, TAG, 'contacts: whitelist stored (%{public}d numbers)', list.length);
    return list.length;
  }

  whitelist(): string[] {
    try {
      return JSON.parse(this.prefs.getSync(KEY_WHITELIST, '[]') as string) as string[];
    } catch (e) {
      return [];
    }
  }
}
