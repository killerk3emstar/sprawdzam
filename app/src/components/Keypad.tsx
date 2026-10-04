/**
 * Big numeric keypad for the family password (no system keyboard needed): light grey keys, near-black digits,
 * the Send key in near-black as the one primary action.
 *
 * @format
 */

import React from 'react';
import {Pressable, StyleSheet, Text, View} from 'react-native';
import {colors, font, size} from '../theme';

type Props = {
  onDigit: (digit: string) => void;
  onDelete: () => void;
  onSubmit: () => void;
  deleteLabel: string;
  submitLabel: string;
  submitDisabled: boolean;
};

const ROWS = [
  ['1', '2', '3'],
  ['4', '5', '6'],
  ['7', '8', '9'],
];

function Key({label, onPress, accessibilityLabel, variant = 'digit', disabled}: {
  label: string;
  onPress: () => void;
  accessibilityLabel?: string;
  variant?: 'digit' | 'action' | 'submit';
  disabled?: boolean;
}): React.JSX.Element {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      disabled={disabled}
      onPress={onPress}
      testID={`key-${accessibilityLabel ?? label}`}
      style={({pressed}) => [
        styles.key,
        variant === 'submit' ? styles.submit : null,
        {opacity: disabled ? 0.4 : pressed ? 0.7 : 1},
      ]}>
      <Text
        style={[
          styles.keyLabel,
          variant !== 'digit' ? styles.smallLabel : null,
          variant === 'submit' ? styles.submitLabel : null,
        ]}>
        {label}
      </Text>
    </Pressable>
  );
}

export function Keypad({onDigit, onDelete, onSubmit, deleteLabel, submitLabel, submitDisabled}: Props): React.JSX.Element {
  return (
    <View style={styles.pad}>
      {ROWS.map(row => (
        <View key={row.join('')} style={styles.row}>
          {row.map(d => (
            <Key key={d} label={d} onPress={() => onDigit(d)} />
          ))}
        </View>
      ))}
      <View style={styles.row}>
        <Key label={deleteLabel} variant="action" onPress={onDelete} />
        <Key label="0" onPress={() => onDigit('0')} />
        <Key label={submitLabel} variant="submit" onPress={onSubmit} disabled={submitDisabled} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  pad: {gap: 8},
  row: {flexDirection: 'row', gap: 8},
  key: {
    flex: 1,
    minHeight: 64,
    borderRadius: size.radius,
    backgroundColor: colors.quiet,
    alignItems: 'center',
    justifyContent: 'center',
  },
  submit: {backgroundColor: colors.ink},
  keyLabel: {color: colors.ink, fontSize: 36, fontWeight: '600'},
  smallLabel: {fontSize: font.body, fontWeight: '700'},
  submitLabel: {color: colors.onColor},
});
