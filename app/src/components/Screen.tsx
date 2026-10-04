/**
 * Page frame for the senior UI. `Screen` is the white page; `Band` is the one strong move: on warning or
 * danger the top of the screen takes the state colour (amber / red) with white text. The status bar follows
 * the colour of whatever touches it.
 *
 * @format
 */

import React from 'react';
import {SafeAreaView, StatusBar, StyleSheet, View, type StyleProp, type ViewStyle} from 'react-native';
import {colors, size} from '../theme';

export type Tone = 'plain' | 'green' | 'amber' | 'red';

export const TONE_BG: Record<Tone, string> = {
  plain: colors.paper,
  green: colors.green,
  amber: colors.amber,
  red: colors.red,
};

export function toneText(tone: Tone): string {
  return tone === 'plain' ? colors.ink : colors.onColor;
}

type ScreenProps = {
  /** Colour of the area under the status bar (the band's tone when the screen starts with a band). */
  top?: Tone;
  /** Whole-screen colour (e.g. the red "this looks like a scam" screen). */
  fill?: Tone;
  children: React.ReactNode;
  testID?: string;
};

export function Screen({top = 'plain', fill = 'plain', children, testID}: ScreenProps): React.JSX.Element {
  const statusTone = fill !== 'plain' ? fill : top;
  return (
    <SafeAreaView style={[styles.root, {backgroundColor: TONE_BG[fill]}]} testID={testID}>
      <StatusBar
        barStyle={statusTone === 'plain' ? 'dark-content' : 'light-content'}
        backgroundColor={TONE_BG[statusTone]}
      />
      {children}
    </SafeAreaView>
  );
}

export function Band({tone, children, style}: {tone: Tone; children: React.ReactNode; style?: StyleProp<ViewStyle>}): React.JSX.Element {
  return <View style={[styles.band, {backgroundColor: TONE_BG[tone]}, style]}>{children}</View>;
}

const styles = StyleSheet.create({
  root: {flex: 1},
  band: {paddingHorizontal: size.side, paddingTop: 28, paddingBottom: 32},
});
