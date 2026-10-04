import {parseConfigLink, toControlUrl} from '../src/deepLink';

test('maps tunnel origins to the control URL', () => {
  expect(toControlUrl('https://abc.trycloudflare.com')).toBe('wss://abc.trycloudflare.com/app/control');
  expect(toControlUrl('http://localhost:8765/')).toBe('ws://localhost:8765/app/control');
  expect(toControlUrl('wss://h.example/app/control')).toBe('wss://h.example/app/control');
  expect(toControlUrl('not a url')).toBeNull();
});

test('parses sprawdzam://config links', () => {
  expect(parseConfigLink('sprawdzam://config?url=https%3A%2F%2Fabc.trycloudflare.com')).toEqual({
    controlUrl: 'wss://abc.trycloudflare.com/app/control',
  });
  expect(parseConfigLink('sprawdzam://config?token=0123456789abcdef')).toEqual({deviceToken: '0123456789abcdef'});
  expect(parseConfigLink('sprawdzam://config?token=short')).toBeNull();
  expect(parseConfigLink('https://example.com')).toBeNull();
});
