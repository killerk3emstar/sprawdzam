/**
 * confirm_block (no family password configured): the whole screen turns red, "To wygląda na oszustwo.
 * Rozłączam za 8 s" counts down, and one huge "Rozłącz teraz" ends the call at once. There is deliberately
 * no "continue" option. The backend ends the call at zero (call_ended scam_blocked); if that has not happened
 * a few seconds later, the app hangs up itself.
 *
 * @format
 */

import React, {useEffect, useRef} from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {BigButton} from '../components/BigButton';
import {Screen} from '../components/Screen';
import {useI18n} from '../i18n';
import {useCountdown} from '../useCountdown';
import {colors, font, size} from '../theme';

const LOCAL_HANGUP_AFTER_MS = 3000;

export function ConfirmBlockScreen({deadline, onHangup}: {deadline: number; onHangup: () => void}): React.JSX.Element {
  const {t} = useI18n();
  const left = useCountdown(deadline) ?? 0;
  const hungUp = useRef(false);

  const hangupOnce = () => {
    if (!hungUp.current) {
      hungUp.current = true;
      onHangup();
    }
  };

  useEffect(() => {
    const timer = setTimeout(hangupOnce, Math.max(0, deadline - Date.now()) + LOCAL_HANGUP_AFTER_MS);
    return () => clearTimeout(timer);
  }, [deadline]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <Screen fill="red" testID="confirm-block-screen">
      <View style={styles.top} accessibilityRole="alert" accessibilityLiveRegion="assertive">
        <Text style={styles.title} accessibilityRole="header">
          {t('blockTitle')}
        </Text>
        <Text style={styles.countdown} testID="block-countdown">
          {left > 0 ? t('blockCountdown', {n: left}) : t('blockEnding')}
        </Text>
        <Text style={styles.advice}>{t('doNotGive')}</Text>
      </View>
      <View style={styles.footer}>
        <BigButton label={t('blockNow')} onPress={hangupOnce} variant="inverse" tall style={styles.huge} testID="block-now" />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  top: {flex: 1, paddingHorizontal: size.side, paddingTop: 72},
  title: {fontSize: font.huge, lineHeight: 56, fontWeight: '700', color: colors.onColor},
  countdown: {fontSize: font.title, lineHeight: 50, color: colors.onColor, marginTop: 24, fontVariant: ['tabular-nums']},
  advice: {fontSize: font.body, lineHeight: 36, color: colors.onColor, marginTop: 32},
  footer: {paddingHorizontal: size.side, paddingBottom: 32},
  huge: {minHeight: 128},
});
