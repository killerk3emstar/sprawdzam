import {STRINGS, translate, translateReason} from '../src/i18n';

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
