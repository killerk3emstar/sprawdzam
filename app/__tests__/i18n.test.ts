import {riskSentence, STRINGS, translate, translateReason} from '../src/i18n';

test('every key has a non-empty Polish and English string', () => {
  const plKeys = Object.keys(STRINGS.pl).sort();
  expect(Object.keys(STRINGS.en).sort()).toEqual(plKeys);
  for (const key of plKeys) {
    expect(STRINGS.pl[key as keyof typeof STRINGS.pl].length).toBeGreaterThan(0);
    expect(STRINGS.en[key as keyof typeof STRINGS.en].length).toBeGreaterThan(0);
  }
});

test('interpolates variables and translates risk reasons', () => {
  expect(translate('en', 'whitelistCount', {n: 3})).toBe('Numbers from contacts: 3');
  expect(translateReason('pl', 'money')).toBe('prośba o pieniądze');
  expect(translateReason('en', 'something_new')).toBe('something_new');
});

test('risk as one plain sentence', () => {
  expect(riskSentence('pl', 'warn', ['money', 'urgency'])).toBe('Uwaga: rozmówca prosi o pieniądze i ponagla Cię.');
  expect(riskSentence('en', 'high', ['authority', 'money', 'secrecy'])).toBe(
    'High scam risk: the caller claims to be police or a bank, asks for money and asks you to keep it secret.',
  );
  expect(riskSentence('pl', 'warn', ['unknown_code'])).toBe('Uwaga: ta rozmowa może być oszustwem.');
  expect(riskSentence('en', 'high', [])).toBe('High scam risk.');
});
