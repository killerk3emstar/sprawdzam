/**
 * Result of a call: clear explanation (blocked scam, missed call, ...) and an OK button.
 *
 * @format
 */

import React from 'react';
import {SafeAreaView, StatusBar, StyleSheet, Text, View} from 'react-native';
import {BigButton} from '../components/BigButton';
import {useI18n, type StringKey} from '../i18n';
import {colors, font, size} from '../theme';

const TITLES: Record<string, StringKey> = {
  scam_blocked: 'ended_scam_blocked_title',
  caller_hangup: 'ended_caller_hangup',
  senior_hangup: 'ended_senior_hangup',
  timeout: 'ended_timeout',
  error: 'ended_error',
};

const ICONS: Record<string, string> = {scam_blocked: '!', timeout: '☎', error: '!'};

export function CallEndedScreen({reason, onOk}: {reason: string; onOk: () => void}): React.JSX.Element {
  const {t} = useI18n();
  const blocked = reason === 'scam_blocked';
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
        {blocked ? <Text style={[styles.text, styles.onRed]}>{t('ended_scam_blocked_text')}</Text> : null}
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
  footer: {paddingBottom: 32},
});
