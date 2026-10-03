/**
 * Design tokens for the senior UI: large type, big touch targets, WCAG AA contrast.
 * Contrast ratios (text on background): white on green 8.9:1, black on amber 10.9:1, white on red 6.6:1,
 * white on blue 8.6:1, white on callBackground 17:1, muted on background 9.3:1.
 */
export const colors = {
  background: '#FFFFFF',
  surface: '#F2F5F8',
  text: '#111111',
  muted: '#3D4A57',
  border: '#8A97A4',
  primary: '#0B4F8A',
  onPrimary: '#FFFFFF',
  green: '#1B5E20',
  onGreen: '#FFFFFF',
  amber: '#FFB300',
  onAmber: '#111111',
  red: '#B71C1C',
  onRed: '#FFFFFF',
  callBackground: '#0F1720',
  onCall: '#FFFFFF',
  onCallMuted: '#C9D3DD',
};

export const font = {
  body: 24,
  large: 30,
  title: 40,
  huge: 52,
};

export const size = {
  touch: 72, // >= 56 dp minimum, larger for seniors
  radius: 18,
  gap: 16,
  padding: 24,
};
