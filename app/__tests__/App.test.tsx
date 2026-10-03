/**
 * @format
 */

import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import App from '../App';

test('renders the app name and the bilingual tagline', async () => {
  let renderer: ReactTestRenderer.ReactTestRenderer | undefined;
  await ReactTestRenderer.act(() => {
    renderer = ReactTestRenderer.create(<App />);
  });
  const json = JSON.stringify(renderer!.toJSON());
  expect(json).toContain('Sprawdzam');
  expect(json).toContain('Second Ear');
  expect(json).toContain('Ochrona przed oszustwami telefonicznymi');
  expect(json).toContain('Protection against phone scams');
});
