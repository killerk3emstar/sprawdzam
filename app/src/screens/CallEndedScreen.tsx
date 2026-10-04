/**
 * Result of a call: clear explanation (blocked scam, missed call, ...) and an OK button.
 *
 * @format
 */

import React from 'react';
import {SafeAreaView, StatusBar, StyleSheet, Text, View} from 'react-native';
import {BigButton} from '../components/BigButton';
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

const ICONS: Record<string, string> = {scam_blocked: '!', timeout: '☎', error: '!'};

const SMS_ERRORS: Record<string, StringKey> = {
  no_permission: 'smsNoPermission',
  no_number: 'smsNoNumber',
  send_failed: 'smsFailed',
};

type Props = {
  reason: string;
  /** Result of the SMS to the trusted person for this call, if the backend asked for one. */
  trustedAlert: TrustedAlert | null;
  onOk: () => void;
};

export function CallEndedScreen({reason, trustedAlert, onOk}: Props): React.JSX.Element {
  const {t} = useI18n();
  const blocked = reason === 'scam_blocked';
  const name = trustedAlert?.name || t('trustedPerson');
  const smsText = trustedAlert
    ? trustedAlert.sent
      ? t('smsSent', {name})
      : t(SMS_ERRORS[trustedAlert.error ?? ''] ?? 'smsFailed', {name})
    : null;
  return (
    <SafeAreaView style={[styles.root, blocked ? styles.blocked : null]} testID="ended-screen">
      <View style={styles.inner}>
      <StatusBar
        barStyle={blocked ? 'light-content' : 'dark-content'}
        backgroundColor={blocked ? colors.red : colors.background}
      />
      <View style={styles.center}>
        <Text style={[styles.icon, blocked ? styles.onRed : null]}>{ICONS[reason] ?? '✓'}</Text>
        <Text style={[styles.title, blocked ? styles.onRed : null]} accessibilityRole="header">
          {t(TITLES[reason] ?? 'ended_senior_hangup')}
        </Text>
        {blocked && !trustedAlert ? (
          <Text style={[styles.text, styles.onRed]}>{t('ended_scam_blocked_text')}</Text>
        ) : null}
        {smsText ? (
          <View style={[styles.sms, trustedAlert?.sent ? styles.smsOk : styles.smsFail]} testID="sms-result">
            <Text
              style={[styles.smsText, {color: trustedAlert?.sent ? colors.onGreen : colors.onAmber}]}
              accessibilityLiveRegion="polite">
              {smsText}
            </Text>
          </View>
        ) : null}
      </View>
      <View style={styles.footer}>
        <BigButton label={t('ok')} onPress={onOk} variant={blocked ? 'neutral' : 'primary'} tall testID="ended-ok" />
      </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: colors.background},
  inner: {flex: 1, paddingHorizontal: size.padding},
  blocked: {backgroundColor: colors.red},
  center: {flex: 1, alignItems: 'center', justifyContent: 'center'},
  icon: {fontSize: 96, fontWeight: '800', color: colors.primary},
  title: {fontSize: font.title, fontWeight: '800', color: colors.text, textAlign: 'center', marginTop: 12},
  text: {fontSize: font.large, color: colors.text, textAlign: 'center', marginTop: 20, lineHeight: 40},
  onRed: {color: colors.onRed},
  sms: {marginTop: 24, borderRadius: 18, paddingVertical: 16, paddingHorizontal: 20, alignSelf: 'stretch'},
  smsOk: {backgroundColor: colors.green},
  smsFail: {backgroundColor: colors.amber},
  smsText: {fontSize: font.large, fontWeight: '800', textAlign: 'center', lineHeight: 36},
  footer: {paddingBottom: 32},
});
