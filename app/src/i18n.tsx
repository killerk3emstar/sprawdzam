/**
 * Minimal i18n: all PL/EN UI strings in one place, selected by the language from settings.
 *
 * @format
 */

import React, {createContext, useContext, useMemo} from 'react';

export type Lang = 'pl' | 'en';

const pl = {
  appName: 'Sprawdzam',
  protectedTitle: 'Jesteś chroniony',
  protectedText: 'Sprawdzamy rozmowy z nieznanych numerów.',
  unavailableTitle: 'Ochrona chwilowo niedostępna',
  unavailableText: 'Rozmowy przechodzą bez sprawdzania. Łączymy ponownie.',
  settings: 'Ustawienia',
  incomingTitle: 'Połączenie przychodzące',
  incomingProtected: 'Rozmowa chroniona przez Sprawdzam',
  hiddenNumber: 'Numer ukryty',
  accept: 'Odbierz',
  reject: 'Odrzuć',
  connecting: 'Łączenie…',
  callChecking: 'Sprawdzamy tę rozmowę',
  riskWarn: 'Uwaga: ta rozmowa może być oszustwem',
  riskHigh: 'Wysokie ryzyko oszustwa! Nie podawaj pieniędzy ani kodów.',
  riskHighShort: 'Wysokie ryzyko oszustwa!',
  reason_money: 'prośba o pieniądze',
  reason_secrecy: 'każe zachować tajemnicę',
  reason_authority: 'podaje się za policję lub bank',
  reason_urgency: 'pośpiech',
  askPassword: 'Zapytaj rozmówcę o hasło rodzinne',
  send: 'Wyślij',
  deleteDigit: 'Usuń',
  passwordSent: 'Hasło wysłane',
  enterAgain: 'Wpisz ponownie',
  hangup: 'Rozłącz',
  ended_scam_blocked_title: 'Rozłączyliśmy podejrzaną rozmowę',
  ended_scam_blocked_text: 'Nie oddzwaniaj na ten numer. Nie podawaj pieniędzy ani kodów.',
  ended_caller_hangup: 'Rozmówca się rozłączył',
  ended_senior_hangup: 'Rozmowa zakończona',
  ended_timeout: 'Nieodebrane połączenie',
  ended_error: 'Połączenie zostało przerwane',
  ok: 'OK',
  language: 'Język',
  trustedPerson: 'Osoba zaufana',
  notChosen: 'Nie wybrano',
  chooseFromContacts: 'Wybierz z kontaktów',
  whitelist: 'Kontakty dzwonią normalnie',
  whitelistCount: 'Numerów z kontaktów: {n}',
  syncContacts: 'Wybierz kontakty',
  notifications: 'Powiadomienia',
  enableNotifications: 'Włącz powiadomienia',
  notificationsOn: 'Powiadomienia włączone',
  developer: 'Dla deweloperów',
  backendUrl: 'Adres serwera',
  deviceToken: 'Token urządzenia',
  saveAndConnect: 'Zapisz i połącz',
  devPanel: 'Panel testowy',
  systemCallUi: 'Systemowy ekran połączenia (test)',
  on: 'Włączone',
  off: 'Wyłączone',
  back: 'Wróć',
  saved: 'Zapisano',
  failed: 'Nie udało się',
  micDenied: 'Brak dostępu do mikrofonu',
  smsSent: 'Wysłano SMS do: {name} ✓',
  smsNoPermission: 'Nie wysłano SMS: brak zgody na wysyłanie SMS',
  smsNoNumber: 'Nie wysłano SMS: nie wybrano osoby zaufanej',
  smsFailed: 'Nie udało się wysłać SMS do: {name}',
  smsPermissionTitle: 'Zgoda na SMS',
  smsPermissionText: 'Sprawdzam wyśle SMS do osoby zaufanej, gdy wykryje oszustwo.',
  smsPermissionOn: 'SMS do osoby zaufanej: włączone',
  smsPermissionOff: 'Zezwól na SMS do osoby zaufanej',
};

export type StringKey = keyof typeof pl;

const en: Record<StringKey, string> = {
  appName: 'Sprawdzam',
  protectedTitle: 'You are protected',
  protectedText: 'We check calls from unknown numbers.',
  unavailableTitle: 'Protection temporarily unavailable',
  unavailableText: 'Calls go through unchecked. Reconnecting.',
  settings: 'Settings',
  incomingTitle: 'Incoming call',
  incomingProtected: 'Call protected by Sprawdzam',
  hiddenNumber: 'Hidden number',
  accept: 'Answer',
  reject: 'Decline',
  connecting: 'Connecting…',
  callChecking: 'We are checking this call',
  riskWarn: 'Warning: this call may be a scam',
  riskHigh: 'High scam risk! Do not give money or codes.',
  riskHighShort: 'High scam risk!',
  reason_money: 'asks for money',
  reason_secrecy: 'asks you to keep it secret',
  reason_authority: 'claims to be police or a bank',
  reason_urgency: 'pressure to hurry',
  askPassword: 'Ask the caller for the family password',
  send: 'Send',
  deleteDigit: 'Delete',
  passwordSent: 'Password sent',
  enterAgain: 'Enter again',
  hangup: 'Hang up',
  ended_scam_blocked_title: 'We ended a suspicious call',
  ended_scam_blocked_text: 'Do not call this number back. Do not give money or codes.',
  ended_caller_hangup: 'The caller hung up',
  ended_senior_hangup: 'Call ended',
  ended_timeout: 'Missed call',
  ended_error: 'The call was interrupted',
  ok: 'OK',
  language: 'Language',
  trustedPerson: 'Trusted person',
  notChosen: 'Not chosen',
  chooseFromContacts: 'Choose from contacts',
  whitelist: 'Contacts ring normally',
  whitelistCount: 'Numbers from contacts: {n}',
  syncContacts: 'Choose contacts',
  notifications: 'Notifications',
  enableNotifications: 'Turn on notifications',
  notificationsOn: 'Notifications are on',
  developer: 'Developer',
  backendUrl: 'Server address',
  deviceToken: 'Device token',
  saveAndConnect: 'Save and connect',
  devPanel: 'Test panel',
  systemCallUi: 'System call screen (test)',
  on: 'On',
  off: 'Off',
  back: 'Back',
  saved: 'Saved',
  failed: 'Failed',
  micDenied: 'No microphone access',
  smsSent: 'Text message sent to: {name} ✓',
  smsNoPermission: 'No text message sent: SMS permission is off',
  smsNoNumber: 'No text message sent: no trusted person chosen',
  smsFailed: 'Could not send the text message to: {name}',
  smsPermissionTitle: 'SMS permission',
  smsPermissionText: 'Sprawdzam texts your trusted person when it detects a scam.',
  smsPermissionOn: 'Text to trusted person: on',
  smsPermissionOff: 'Allow texting the trusted person',
};

export const STRINGS: Record<Lang, Record<StringKey, string>> = {pl, en};

export function translate(lang: Lang, key: StringKey, vars?: Record<string, string | number>): string {
  let text = STRINGS[lang][key] ?? STRINGS.pl[key] ?? key;
  if (vars) {
    for (const [name, value] of Object.entries(vars)) {
      text = text.replace(`{${name}}`, String(value));
    }
  }
  return text;
}

/** Translates a backend reason code (money, secrecy, authority, urgency); unknown codes are shown as is. */
export function translateReason(lang: Lang, reason: string): string {
  const key = `reason_${reason}` as StringKey;
  return key in STRINGS.pl ? translate(lang, key) : reason;
}

type I18n = {
  lang: Lang;
  t: (key: StringKey, vars?: Record<string, string | number>) => string;
};

const I18nContext = createContext<I18n>({lang: 'pl', t: (key, vars) => translate('pl', key, vars)});

export function I18nProvider({lang, children}: {lang: Lang; children: React.ReactNode}): React.JSX.Element {
  const value = useMemo<I18n>(() => ({lang, t: (key, vars) => translate(lang, key, vars)}), [lang]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  return useContext(I18nContext);
}
