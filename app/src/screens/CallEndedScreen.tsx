/**
 * Result of a call. For a blocked scam: red band "Rozłączyliśmy podejrzaną rozmowę", the SMS result, plain
 * advice, and "Zadzwoń do: {trusted person}" which opens the dialer with their number (police advice: hang
 * up, then call the relative back on a number you know). Other endings: one plain sentence and OK.
 *
 * @format
 */

import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {BigButton} from '../components/BigButton';
import {Band, Screen} from '../components/Screen';
import {useI18n, type StringKey} from '../i18n';
import type {TrustedAlert} from '../native/CallEngine';
import {colors, font, size} from '../theme';

const TITLES: Record<string, StringKey> = {
  scam_blocked: 'ended_scam_blocked_title',
  caller_hangup: 'ended_caller_hangup',
  senior_hangup: 'ended_senior_hangup',
  timeout: 'ended_timeout',
  error: 'ended_error',
};

const SMS_ERRORS: Record<string, StringKey> = {
  no_permission: 'smsNoPermission',
  no_number: 'smsNoNumber',
  send_failed: 'smsFailed',
};

type Props = {
  reason: string;
  /** Result of the SMS to the trusted person for this call, if the backend asked for one. */
  trustedAlert: TrustedAlert | null;
  /** Trusted person from settings; enables "Call {name}" after a blocked scam. */
  trustedPerson: {name: string; number: string} | null;
  onCallTrusted: (number: string) => void;
  onOk: () => void;
};

export function CallEndedScreen({reason, trustedAlert, trustedPerson, onCallTrusted, onOk}: Props): React.JSX.Element {
  const {t} = useI18n();
  const blocked = reason === 'scam_blocked';
  const title = t(TITLES[reason] ?? 'ended_senior_hangup');

  if (!blocked) {
    return (
      <Screen testID="ended-screen">
        <View style={styles.plainTop}>
          <Text style={styles.plainTitle} accessibilityRole="header">
            {title}
          </Text>
        </View>
        <View style={styles.footer}>
          <BigButton label={t('ok')} onPress={onOk} tall testID="ended-ok" />
        </View>
      </Screen>
    );
  }

  const name = trustedAlert?.name || trustedPerson?.name || t('trustedPerson');
  const smsText = trustedAlert
    ? trustedAlert.sent
      ? t('smsSent', {name})
      : t(SMS_ERRORS[trustedAlert.error ?? ''] ?? 'smsFailed', {name})
    : null;

  return (
    <Screen top="red" testID="ended-screen">
      <Band tone="red" style={styles.band}>
        <Text style={styles.blockedTitle} accessibilityRole="header">
          {title}
        </Text>
      </Band>
      <View style={styles.body}>
        {smsText ? (
          <Text
            style={[styles.sms, {color: trustedAlert?.sent ? colors.green : colors.amber}]}
            accessibilityLiveRegion="polite"
            testID="sms-result">
            {smsText}
          </Text>
        ) : null}
        <Text style={styles.advice}>{t('ended_scam_blocked_text')}</Text>
      </View>
      <View style={styles.footer}>
        {trustedPerson?.number ? (
          <BigButton
            label={t('callTrusted', {name: trustedPerson.name})}
            accessibilityHint={t('callTrustedHint')}
            onPress={() => onCallTrusted(trustedPerson.number)}
            tall
            testID="call-trusted"
          />
        ) : null}
        <BigButton
          label={t('ok')}
          onPress={onOk}
          variant={trustedPerson?.number ? 'quiet' : 'primary'}
          tall={!trustedPerson?.number}
          testID="ended-ok"
        />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  plainTop: {flex: 1, paddingHorizontal: size.side, paddingTop: 120},
  plainTitle: {fontSize: font.title, lineHeight: 50, fontWeight: '700', color: colors.ink},
  band: {paddingTop: 72, paddingBottom: 40},
  blockedTitle: {fontSize: font.title, lineHeight: 50, fontWeight: '700', color: colors.onColor},
  body: {flex: 1, paddingHorizontal: size.side, paddingTop: 28},
  sms: {fontSize: font.body, lineHeight: 36, fontWeight: '700', marginBottom: 20},
  advice: {fontSize: font.body, lineHeight: 36, color: colors.ink, maxWidth: 520},
  footer: {gap: size.gap, paddingHorizontal: size.side, paddingBottom: 32},
});
