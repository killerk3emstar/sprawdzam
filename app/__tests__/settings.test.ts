import {DEFAULT_SETTINGS, parseSettings} from '../src/settings';

test('defaults for an empty or broken store', () => {
  expect(parseSettings('{}')).toEqual(DEFAULT_SETTINGS);
  expect(parseSettings('not json')).toEqual(DEFAULT_SETTINGS);
  expect(DEFAULT_SETTINGS.deviceToken.length).toBeGreaterThanOrEqual(16);
});

test('legacy dev defaults are migrated, custom values are kept', () => {
  const legacy = parseSettings('{"controlUrl":"ws://127.0.0.1:8765/app/control","deviceToken":"dev-device-1"}');
  expect(legacy.controlUrl).toBe('ws://localhost:8765/app/control');
  expect(legacy.deviceToken).toBe('dev-device-1-sprawdzam');
  const custom = parseSettings('{"controlUrl":"wss://example.org/app/control","deviceToken":"a-very-long-secret-token","lang":"en"}');
  expect(custom.controlUrl).toBe('wss://example.org/app/control');
  expect(custom.deviceToken).toBe('a-very-long-secret-token');
  expect(custom.lang).toBe('en');
});
