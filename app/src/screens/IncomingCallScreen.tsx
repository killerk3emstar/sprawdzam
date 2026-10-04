/**
 * Incoming protected call: who is calling (masked number), one sentence about the protection, and two
 * full-width buttons, Answer (green) and Decline (quiet).
 *
 * @format
 */

import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {BigButton} from '../components/BigButton';
import {Screen} from '../components/Screen';
import {useI18n} from '../i18n';
import {colors, font, size} from '../theme';

type Props = {
  caller: string;
  connecting: boolean;
  error: string | null;
  onAccept: () => void;
  onReject: () => void;
};

export function IncomingCallScreen({caller, connecting, error, onAccept, onReject}: Props): React.JSX.Element {
  const {t} = useI18n();
  const shown = !caller || caller === 'unknown' ? t('hiddenNumber') : caller;
  return (
    <Screen testID="incoming-screen">
      <View style={styles.top} accessibilityLiveRegion="assertive">
        <Text style={styles.label}>{t('incomingTitle')}</Text>
        <Text
          style={styles.caller}
          accessibilityRole="header"
          numberOfLines={1}
          adjustsFontSizeToFit
          minimumFontScale={0.6}>
          {shown}
        </Text>
        <Text style={styles.text}>{t('incomingProtected')}</Text>
        {error ? <Text style={styles.error}>{error}</Text> : null}
      </View>
      <View style={styles.actions}>
        <BigButton
          label={connecting ? t('connecting') : t('accept')}
          onPress={onAccept}
          variant="go"
          disabled={connecting}
          tall
          testID="accept-call"
        />
        <BigButton label={t('reject')} onPress={onReject} variant="quiet" tall testID="reject-call" />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  top: {flex: 1, paddingHorizontal: size.side, paddingTop: 64},
  label: {fontSize: font.small, color: colors.muted},
  // 48 pt, shrinks to fit so a masked number ("+48 *** *** 123") stays on one line on a 360 dp phone.
  caller: {fontSize: font.huge, fontWeight: '700', color: colors.ink, marginTop: 12},
  text: {fontSize: font.body, lineHeight: 36, color: colors.ink, marginTop: 32, maxWidth: 520},
  error: {fontSize: font.small, lineHeight: 32, color: colors.red, marginTop: 24},
  actions: {gap: size.gap, paddingHorizontal: size.side, paddingBottom: 32},
});
