/**
 * @format
 */

import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import App from '../App';

// Without the native module (plain Jest) the app falls back to default settings and
// shows the amber "protection unavailable" state (fail-open).
test('renders the home screen with the unavailable status when CallEngine is missing', async () => {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    renderer = ReactTestRenderer.create(<App />);
  });
  const json = JSON.stringify(renderer.toJSON());
  expect(json).toContain('Sprawdzam');
  expect(json).toContain('Ochrona chwilowo niedostępna');
  expect(json).toContain('Ustawienia');
});
