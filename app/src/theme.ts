/**
 * Design tokens for the senior UI.
 *
 * White page, near-black text, system font, left-aligned. Colour is used only for meaning:
 * green = protected / OK, amber = warning, red = danger / blocked. On warning and danger the top of the
 * screen takes that colour with white text; nothing else is coloured.
 *
 * Contrast (WCAG): ink on paper 17.4:1, muted on paper 7.5:1, white on green 6.5:1, white on amber 5.8:1,
 * white on red 6.5:1, ink on quiet button 14.7:1, green text on paper 6.5:1. All pass AA for body text.
 */
export const colors = {
  paper: '#FFFFFF',
  ink: '#1A1A1A',
  muted: '#555555',
  quiet: '#ECECEC', // secondary button fill
  green: '#1B6B3A',
  amber: '#A04F00',
  red: '#B3261E',
  onColor: '#FFFFFF',
};

export const font = {
  small: 24, // never below 24 (team decision)
  body: 26,
  lead: 32,
  title: 40,
  huge: 48,
};

export const size = {
  button: 72, // >= 64 dp
  buttonTall: 96,
  radius: 14,
  side: 24,
  gap: 16,
};
