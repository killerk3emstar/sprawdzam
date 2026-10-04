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
  unavailableText: 'Rozmowy przechodzą bez sprawdzania. Próbujemy połączyć się ponownie.',
  settings: 'Ustawienia',
  incomingTitle: 'Dzwoni nieznany numer',
  incomingProtected: 'Sprawdzamy tę rozmowę i ostrzeżemy Cię, jeśli coś będzie nie tak.',
  hiddenNumber: 'Numer ukryty',
  accept: 'Odbierz',
  reject: 'Odrzuć',
  connecting: 'Łączenie…',
  callChecking: 'Sprawdzamy tę rozmowę',
  riskWarn: 'Uwaga: ta rozmowa może być oszustwem.',
  riskHigh: 'Duże ryzyko oszustwa.',
  riskHighShort: 'Duże ryzyko oszustwa',
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
  smsSent: 'Wysłaliśmy SMS do: {name}',
  smsNoPermission: 'Nie wysłano SMS: brak zgody na wysyłanie SMS',
  smsNoNumber: 'Nie wysłano SMS: nie wybrano osoby zaufanej',
  smsFailed: 'Nie udało się wysłać SMS do: {name}',
  smsPermissionTitle: 'Zgoda na SMS',
  smsPermissionText: 'Sprawdzam wyśle SMS do osoby zaufanej, gdy wykryje oszustwo.',
  smsPermissionOn: 'SMS do osoby zaufanej: włączone',
  smsPermissionOff: 'Zezwól na SMS do osoby zaufanej',
  trustedPersonLine: 'Osoba zaufana: {name}',
  noTrustedPerson: 'Nie wybrano osoby zaufanej',
  riskNone: 'Sprawdzamy tę rozmowę. Na razie nic podejrzanego.',
  riskWarnLead: 'Uwaga',
  riskHighLead: 'Duże ryzyko oszustwa',
  callerDoes: 'rozmówca {clauses}.',
  and: ' i ',
  clause_money: 'prosi o pieniądze',
  clause_secrecy: 'każe zachować tajemnicę',
  clause_authority: 'podaje się za policję lub bank',
  clause_urgency: 'ponagla Cię',
  doNotGive: 'Nie podawaj pieniędzy ani kodów.',
  passwordHint: 'Wpisz hasło, które poda.',
  passwordCountdown: 'Zostało {n} s',
  passwordTimeUp: 'Czas minął. Rozłączamy.',
  blockTitle: 'To wygląda na oszustwo',
  blockCountdown: 'Rozłączam za {n} s',
  blockEnding: 'Rozłączam…',
  blockNow: 'Rozłącz teraz',
  callTrusted: 'Zadzwoń do: {name}',
  callTrustedHint: 'Zadzwoń do bliskiej osoby na znany numer i opowiedz o tej rozmowie.',
  callTimer: 'Czas rozmowy {time}',
};

export type StringKey = keyof typeof pl;

const en: Record<StringKey, string> = {
  appName: 'Sprawdzam',
  protectedTitle: 'You are protected',
  protectedText: 'We check calls from unknown numbers.',
  unavailableTitle: 'Protection temporarily unavailable',
  unavailableText: 'Calls go through unchecked. We keep trying to reconnect.',
  settings: 'Settings',
  incomingTitle: 'Unknown number calling',
  incomingProtected: 'We check this call and warn you if something is wrong.',
  hiddenNumber: 'Hidden number',
  accept: 'Answer',
  reject: 'Decline',
  connecting: 'Connecting…',
  callChecking: 'We are checking this call',
  riskWarn: 'Warning: this call may be a scam.',
  riskHigh: 'High scam risk.',
  riskHighShort: 'High scam risk',
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
  smsSent: 'Text message sent to: {name}',
  smsNoPermission: 'No text message sent: SMS permission is off',
  smsNoNumber: 'No text message sent: no trusted person chosen',
  smsFailed: 'Could not send the text message to: {name}',
  smsPermissionTitle: 'SMS permission',
  smsPermissionText: 'Sprawdzam texts your trusted person when it detects a scam.',
  smsPermissionOn: 'Text to trusted person: on',
  smsPermissionOff: 'Allow texting the trusted person',
  trustedPersonLine: 'Trusted person: {name}',
  noTrustedPerson: 'No trusted person chosen',
  riskNone: 'We are checking this call. Nothing suspicious so far.',
  riskWarnLead: 'Warning',
  riskHighLead: 'High scam risk',
  callerDoes: 'the caller {clauses}.',
  and: ' and ',
  clause_money: 'asks for money',
  clause_secrecy: 'asks you to keep it secret',
  clause_authority: 'claims to be police or a bank',
  clause_urgency: 'pushes you to hurry',
  doNotGive: 'Do not give money or codes.',
  passwordHint: 'Type the password they tell you.',
  passwordCountdown: '{n} s left',
  passwordTimeUp: 'Time is up. Hanging up.',
  blockTitle: 'This looks like a scam',
  blockCountdown: 'Hanging up in {n} s',
  blockEnding: 'Hanging up…',
  blockNow: 'Hang up now',
  callTrusted: 'Call {name}',
  callTrustedHint: 'Call someone close on a number you know and tell them about this call.',
  callTimer: 'Call time {time}',
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

/**
 * Risk as one plain sentence: "Uwaga: rozmówca prosi o pieniądze i ponagla Cię." Unknown reason codes are
 * skipped; without known reasons the generic sentence for the level is used.
 */
export function riskSentence(lang: Lang, level: 'warn' | 'high', reasons: string[]): string {
  const clauses = Array.from(new Set(reasons))
    .map(r => `clause_${r}`)
    .filter((k): k is StringKey => k in STRINGS.pl)
    .map(k => translate(lang, k));
  if (clauses.length === 0) {
    return translate(lang, level === 'high' ? 'riskHigh' : 'riskWarn');
  }
  const and = translate(lang, 'and');
  const joined = clauses.length === 1 ? clauses[0] : `${clauses.slice(0, -1).join(', ')}${and}${clauses[clauses.length - 1]}`;
  const lead = translate(lang, level === 'high' ? 'riskHighLead' : 'riskWarnLead');
  return `${lead}: ${translate(lang, 'callerDoes', {clauses: joined})}`;
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
