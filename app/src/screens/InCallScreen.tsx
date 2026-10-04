/**
 * In-call screen: caller, timer, risk banner, family-password keypad on verify_password, big Hang up.
 *
 * @format
 */

import React, {useEffect, useState} from 'react';
import {SafeAreaView, ScrollView, StatusBar, StyleSheet, Text, View} from 'react-native';
import {BigButton} from '../components/BigButton';
import {Keypad} from '../components/Keypad';
import {RiskBanner} from '../components/RiskBanner';
import {useI18n} from '../i18n';
import type {CallView} from '../useCallEngine';
import {colors, font, size} from '../theme';

const MAX_DIGITS = 32;

function formatDuration(ms: number): string {
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

export function InCallScreen({call, onHangup, onSendPassword, onEnterAgain}: Props): React.JSX.Element {
  const {t} = useI18n();
  const [now, setNow] = useState(Date.now());
  const [digits, setDigits] = useState('');

  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, []);

  const caller = !call.caller || call.caller === 'unknown' ? t('hiddenNumber') : call.caller;
  const showKeypad = call.passwordRequested && !call.passwordSent;
  // Once the password is requested everything else shrinks so the keypad and Hang up fit without scrolling.
  const compact = call.passwordRequested;

  return (
    <SafeAreaView style={styles.root} testID="incall-screen">
      <StatusBar barStyle="light-content" backgroundColor={colors.callBackground} />
      <ScrollView contentContainerStyle={styles.content}>
        <View style={compact ? styles.headerRow : null}>
          <Text
            style={[styles.caller, compact ? styles.callerCompact : null]}
            accessibilityRole="header"
            numberOfLines={1}
            adjustsFontSizeToFit
            minimumFontScale={0.6}>
            {caller}
          </Text>
          <Text style={[styles.timer, compact ? styles.timerCompact : null]} testID="call-timer">
            {call.phase === 'active' && call.activeSince ? formatDuration(now - call.activeSince) : t('connecting')}
          </Text>
        </View>

        <RiskBanner risk={call.risk} compact={compact} />

        {call.passwordRequested ? (
          <View style={styles.password} testID="password-panel">
            <Text style={[styles.passwordTitle, compact ? styles.passwordTitleCompact : null]}>{t('askPassword')}</Text>
            {showKeypad ? (
              <>
                <Text style={styles.digits} testID="password-digits">
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
              <View style={styles.sentRow}>
                <Text style={styles.sent}>{t('passwordSent')}</Text>
                <BigButton label={t('enterAgain')} onPress={onEnterAgain} variant="neutral" />
              </View>
            )}
          </View>
        ) : null}
        {call.error ? <Text style={styles.error}>{call.error}</Text> : null}
      </ScrollView>
      <View style={styles.footer}>
        <BigButton label={t('hangup')} onPress={onHangup} variant="red" tall={!compact} testID="hangup-call" />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: colors.callBackground},
  content: {paddingHorizontal: size.padding, paddingTop: 24, paddingBottom: 12},
  caller: {fontSize: font.title, fontWeight: '800', color: colors.onCall, textAlign: 'center'},
  timer: {fontSize: font.large, color: colors.onCallMuted, textAlign: 'center', marginTop: 8},
  headerRow: {flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between'},
  callerCompact: {fontSize: font.body, textAlign: 'left', flexShrink: 1},
  timerCompact: {fontSize: font.body, marginTop: 0, marginLeft: 12},
  password: {marginTop: 12, borderRadius: 18, padding: 14, backgroundColor: '#17222D'},
  passwordTitle: {fontSize: font.large, fontWeight: '800', color: colors.onCall},
  passwordTitleCompact: {fontSize: font.body},
  digits: {
    fontSize: font.title,
    fontWeight: '800',
    color: colors.onCall,
    textAlign: 'center',
    letterSpacing: 8,
    marginTop: 4,
    minHeight: 52,
  },
  sentRow: {gap: 12, marginTop: 12},
  sent: {fontSize: font.large, color: colors.onCall},
  error: {fontSize: font.body, color: '#FFCDD2', marginTop: 16},
  footer: {paddingHorizontal: size.padding, paddingVertical: 16},
});
