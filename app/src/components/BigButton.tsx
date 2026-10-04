/**
 * Full-width button for the senior UI: >= 72 dp tall (96 dp with `tall`), plain label, no border or shadow.
 * Colour follows meaning only: go = answer (green), stop = hang up (red), primary = the main neutral action,
 * quiet = secondary, inverse = white button on a red or amber screen.
 *
 * @format
 */

import React from 'react';
import {Pressable, StyleSheet, Text, type StyleProp, type ViewStyle} from 'react-native';
import {colors, font, size} from '../theme';

type Variant = 'primary' | 'go' | 'stop' | 'quiet' | 'inverse';

const VARIANTS: Record<Variant, {bg: string; fg: string}> = {
  primary: {bg: colors.ink, fg: colors.onColor},
  go: {bg: colors.green, fg: colors.onColor},
  stop: {bg: colors.red, fg: colors.onColor},
  quiet: {bg: colors.quiet, fg: colors.ink},
  inverse: {bg: colors.paper, fg: colors.red},
};

type Props = {
  label: string;
  onPress: () => void;
  variant?: Variant;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
  tall?: boolean;
  /** Overrides the label colour (inverse button on amber). */
  color?: string;
  accessibilityHint?: string;
};

export function BigButton({
  label,
  onPress,
  variant = 'primary',
  disabled,
  style,
  testID,
  tall,
  color,
  accessibilityHint,
}: Props): React.JSX.Element {
  const v = VARIANTS[variant];
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityHint={accessibilityHint}
      accessibilityState={{disabled: !!disabled}}
      disabled={disabled}
      onPress={onPress}
      testID={testID}
      style={({pressed}) => [
        styles.button,
        tall ? styles.tall : null,
        {backgroundColor: v.bg, opacity: disabled ? 0.45 : pressed ? 0.8 : 1},
        style,
      ]}>
      <Text style={[styles.label, tall ? styles.labelTall : null, {color: color ?? v.fg}]}>{label}</Text>
    </Pressable>
  );
}

/** Quiet text action (e.g. "Ustawienia" on Home): underlined, 24 pt, 64 dp touch target. */
export function TextLink({label, onPress, testID}: {label: string; onPress: () => void; testID?: string}): React.JSX.Element {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      onPress={onPress}
      testID={testID}
      hitSlop={8}
      style={({pressed}) => [styles.link, {opacity: pressed ? 0.6 : 1}]}>
      <Text style={styles.linkLabel}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    alignSelf: 'stretch',
    minHeight: size.button,
    borderRadius: size.radius,
    paddingHorizontal: 20,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tall: {minHeight: size.buttonTall},
  label: {fontSize: font.body, fontWeight: '700', textAlign: 'center'},
  labelTall: {fontSize: font.lead},
  link: {minHeight: 64, justifyContent: 'center', alignSelf: 'flex-start'},
  linkLabel: {fontSize: font.small, color: colors.ink, textDecorationLine: 'underline'},
});
