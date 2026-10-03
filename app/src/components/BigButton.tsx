/**
 * Large, high-contrast button for the senior UI (>= 72 dp tall, 30 pt label).
 *
 * @format
 */

import React from 'react';
import {Pressable, StyleSheet, Text, type StyleProp, type ViewStyle} from 'react-native';
import {colors, font, size} from '../theme';

type Variant = 'primary' | 'green' | 'red' | 'neutral';

const VARIANTS: Record<Variant, {bg: string; fg: string; border?: string}> = {
  primary: {bg: colors.primary, fg: colors.onPrimary},
  green: {bg: colors.green, fg: colors.onGreen},
  red: {bg: colors.red, fg: colors.onRed},
  neutral: {bg: colors.background, fg: colors.text, border: colors.border},
};

type Props = {
  label: string;
  onPress: () => void;
  variant?: Variant;
  disabled?: boolean;
  style?: StyleProp<ViewStyle>;
  testID?: string;
  tall?: boolean;
};

export function BigButton({label, onPress, variant = 'primary', disabled, style, testID, tall}: Props): React.JSX.Element {
  const v = VARIANTS[variant];
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      accessibilityState={{disabled: !!disabled}}
      disabled={disabled}
      onPress={onPress}
      testID={testID}
      style={({pressed}) => [
        styles.button,
        tall ? styles.tall : null,
        {backgroundColor: v.bg, borderColor: v.border ?? v.bg, opacity: disabled ? 0.5 : pressed ? 0.85 : 1},
        style,
      ]}>
      <Text style={[styles.label, {color: v.fg}]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  button: {
    minHeight: size.touch,
    borderRadius: size.radius,
    borderWidth: 2,
    paddingHorizontal: 20,
    paddingVertical: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  tall: {
    minHeight: 112,
  },
  label: {
    fontSize: font.large,
    fontWeight: '700',
    textAlign: 'center',
  },
});
