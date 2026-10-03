/**
 * Big numeric keypad for the family password (no system keyboard needed).
 *
 * @format
 */

import React from 'react';
import {Pressable, StyleSheet, Text, View} from 'react-native';
import {colors, font} from '../theme';

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
        variant === 'submit' ? styles.submit : variant === 'action' ? styles.action : null,
        {opacity: disabled ? 0.4 : pressed ? 0.7 : 1},
      ]}>
      <Text style={[styles.keyLabel, variant !== 'digit' ? styles.smallLabel : null]}>{label}</Text>
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
        <Key label="⌫" accessibilityLabel={deleteLabel} variant="action" onPress={onDelete} />
        <Key label="0" onPress={() => onDigit('0')} />
        <Key label={submitLabel} variant="submit" onPress={onSubmit} disabled={submitDisabled} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  pad: {gap: 8, marginTop: 8},
  row: {flexDirection: 'row', gap: 8},
  key: {
    flex: 1,
    minHeight: 64,
    borderRadius: 16,
    backgroundColor: '#25313D',
    alignItems: 'center',
    justifyContent: 'center',
  },
  action: {backgroundColor: '#3A4754'},
  submit: {backgroundColor: colors.green},
  keyLabel: {color: colors.onCall, fontSize: font.title, fontWeight: '700'},
  smallLabel: {fontSize: font.large},
});
