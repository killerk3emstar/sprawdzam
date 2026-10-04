/**
 * Risk banner shown during a call: neutral while checking, amber at "warn", red at "high".
 *
 * @format
 */

import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {translateReason, useI18n} from '../i18n';
import type {RiskUpdate} from '../native/CallEngine';
import {colors, font} from '../theme';

export function RiskBanner({risk, compact}: {risk: RiskUpdate | null; compact?: boolean}): React.JSX.Element {
  const {t, lang} = useI18n();
  const level = risk?.level ?? 'none';
  if (level !== 'warn' && level !== 'high') {
    return (
      <View style={[styles.banner, styles.neutral, compact ? styles.compact : null]} testID="risk-banner-none">
        <Text style={[styles.title, styles.neutralText]}>{t('callChecking')}</Text>
      </View>
    );
  }
  const high = level === 'high';
  const reasons = (risk?.reasons ?? []).map(r => translateReason(lang, r));
  return (
    <View
      style={[styles.banner, high ? styles.high : styles.warn, compact ? styles.compact : null]}
      accessibilityRole="alert"
      accessibilityLiveRegion="assertive"
      testID={high ? 'risk-banner-high' : 'risk-banner-warn'}>
      <Text style={[styles.title, compact ? styles.titleCompact : null, {color: high ? colors.onRed : colors.onAmber}]}>
        {high ? t(compact ? 'riskHighShort' : 'riskHigh') : t('riskWarn')}
      </Text>
      {reasons.length > 0 ? (
        <Text
          style={[styles.reasons, compact ? styles.reasonsCompact : null, {color: high ? colors.onRed : colors.onAmber}]}
          numberOfLines={compact ? 4 : undefined}
          testID="risk-reasons">
          {reasons.join(' · ')}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  banner: {borderRadius: 18, padding: 18, marginTop: 20},
  neutral: {backgroundColor: '#1E2A36'},
  neutralText: {color: colors.onCallMuted},
  warn: {backgroundColor: colors.amber},
  high: {backgroundColor: colors.red},
  title: {fontSize: font.large, fontWeight: '800'},
  compact: {marginTop: 12, padding: 12},
  titleCompact: {fontSize: font.body},
  reasons: {fontSize: font.body, marginTop: 8},
  reasonsCompact: {marginTop: 4},
});
