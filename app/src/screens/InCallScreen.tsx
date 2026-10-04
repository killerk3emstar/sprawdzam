/**
 * In-call screen. Top: masked caller and timer. Below them one plain sentence with the risk level
 * ("Uwaga: rozmówca prosi o pieniądze i ponagla Cię."); at "warn" the top turns amber, at "high" red.
 * On verify_password the keypad for the family password appears with a visible countdown. A big
 * "Rozłącz" is always at the bottom. confirm_block switches to the full-screen ConfirmBlockScreen.
 *
 * @format
 */

import React, {useEffect, useState} from 'react';
import {ScrollView, StyleSheet, Text, View} from 'react-native';
import {BigButton} from '../components/BigButton';
import {Keypad} from '../components/Keypad';
import {Band, Screen, toneText, type Tone} from '../components/Screen';
import {riskSentence, useI18n} from '../i18n';
import {useCountdown} from '../useCountdown';
import type {CallView} from '../useCallEngine';
import {colors, font, size} from '../theme';
import {ConfirmBlockScreen} from './ConfirmBlockScreen';

const MAX_DIGITS = 32;

export function formatDuration(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

type Props = {
  call: CallView;
  onHangup: () => void;
  onSendPassword: (digits: string) => void;
  onEnterAgain: () => void;
};

export function InCallScreen(props: Props): React.JSX.Element {
  if (props.call.blockDeadline !== null) {
    return <ConfirmBlockScreen deadline={props.call.blockDeadline} onHangup={props.onHangup} />;
  }
  return <InCall {...props} />;
}

function InCall({call, onHangup, onSendPassword, onEnterAgain}: Props): React.JSX.Element {
  const {t, lang} = useI18n();
  const [now, setNow] = useState(Date.now());
  const [digits, setDigits] = useState('');
  const left = useCountdown(call.passwordRequested ? call.passwordDeadline : null);

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const level = call.risk?.level;
  const tone: Tone = call.passwordRequested || level === 'high' ? 'red' : level === 'warn' ? 'amber' : 'plain';
  const fg = {color: toneText(tone)};
  const caller = !call.caller || call.caller === 'unknown' ? t('hiddenNumber') : call.caller;
  const time = call.phase === 'active' && call.activeSince ? formatDuration(now - call.activeSince) : t('connecting');
  const showKeypad = call.passwordRequested && !call.passwordSent;

  let sentence = t('riskNone');
  if (level === 'warn' || level === 'high') {
    sentence = riskSentence(lang, level, call.risk?.reasons ?? []);
  }

  return (
    <Screen top={tone} testID="incall-screen">
      <Band tone={tone} style={call.passwordRequested ? styles.bandCompact : null}>
        <View style={styles.header}>
          <Text style={[styles.caller, fg]} accessibilityRole="header" numberOfLines={1} adjustsFontSizeToFit minimumFontScale={0.7}>
            {caller}
          </Text>
          <Text style={[styles.timer, fg]} testID="call-timer" accessibilityLabel={t('callTimer', {time})}>
            {time}
          </Text>
        </View>

        {call.passwordRequested ? (
          <View accessibilityRole="alert" accessibilityLiveRegion="assertive" testID="password-panel">
            <Text style={[styles.statement, fg]}>{t('askPassword')}</Text>
            {left !== null ? (
              <Text style={[styles.countdown, fg]} testID="password-countdown" accessibilityLiveRegion="polite">
                {left > 0 ? t('passwordCountdown', {n: left}) : t('passwordTimeUp')}
              </Text>
            ) : null}
          </View>
        ) : (
          <View
            accessibilityRole={tone === 'plain' ? undefined : 'alert'}
            accessibilityLiveRegion={tone === 'plain' ? 'polite' : 'assertive'}
            testID={`risk-${level === 'warn' || level === 'high' ? level : 'none'}`}>
            <Text style={[tone === 'plain' ? styles.calm : styles.statement, fg]} testID="risk-sentence">
              {sentence}
            </Text>
            {level === 'high' ? <Text style={[styles.advice, fg]}>{t('doNotGive')}</Text> : null}
          </View>
        )}
      </Band>

      <ScrollView style={styles.flex} contentContainerStyle={styles.body} keyboardShouldPersistTaps="handled">
        {call.passwordRequested ? (
          showKeypad ? (
            <>
              <Text style={styles.hint}>{t('passwordHint')}</Text>
              <Text style={styles.digits} testID="password-digits" accessibilityLiveRegion="polite">
                {digits || ' '}
              </Text>
              <Keypad
                onDigit={d => setDigits(prev => (prev.length < MAX_DIGITS ? prev + d : prev))}
                onDelete={() => setDigits(prev => prev.slice(0, -1))}
                onSubmit={() => {
                  onSendPassword(digits);
                  setDigits('');
                }}
                deleteLabel={t('deleteDigit')}
                submitLabel={t('send')}
                submitDisabled={digits.length === 0}
              />
            </>
          ) : (
            <>
              <Text style={styles.sent}>{t('passwordSent')}</Text>
              <BigButton label={t('enterAgain')} onPress={onEnterAgain} variant="quiet" />
            </>
          )
        ) : null}
        {call.error ? <Text style={styles.error}>{call.error}</Text> : null}
      </ScrollView>

      <View style={styles.footer}>
        <BigButton label={t('hangup')} onPress={onHangup} variant="stop" tall={!call.passwordRequested} testID="hangup-call" />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  bandCompact: {paddingTop: 16, paddingBottom: 20},
  header: {flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', gap: 16},
  caller: {flexShrink: 1, fontSize: font.body, fontWeight: '700'},
  timer: {fontSize: font.body, fontVariant: ['tabular-nums']},
  calm: {fontSize: font.lead, lineHeight: 42, marginTop: 48},
  statement: {fontSize: font.lead, lineHeight: 42, fontWeight: '700', marginTop: 28},
  advice: {fontSize: font.body, lineHeight: 36, marginTop: 16},
  countdown: {fontSize: font.body, lineHeight: 34, marginTop: 8, fontVariant: ['tabular-nums']},
  flex: {flex: 1},
  body: {paddingHorizontal: size.side, paddingTop: 16, paddingBottom: 8},
  hint: {fontSize: font.small, lineHeight: 32, color: colors.muted},
  digits: {
    fontSize: 36,
    fontWeight: '700',
    color: colors.ink,
    letterSpacing: 8,
    minHeight: 52,
    marginVertical: 4,
  },
  sent: {fontSize: font.body, lineHeight: 36, color: colors.ink, marginBottom: 16},
  error: {fontSize: font.small, lineHeight: 32, color: colors.red, marginTop: 16},
  footer: {paddingHorizontal: size.side, paddingTop: 8, paddingBottom: 24},
});
