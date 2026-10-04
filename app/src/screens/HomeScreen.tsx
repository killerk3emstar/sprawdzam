/**
 * Home: one statement. "Jesteś chroniony" (green text on white) or, when the backend is unreachable, an amber
 * band "Ochrona chwilowo niedostępna". Trusted person small below, settings as a quiet text link.
 * Long-press the app name for 2 s to open the developer panel.
 *
 * @format
 */

import React from 'react';
import {Pressable, StyleSheet, Text, View} from 'react-native';
import {TextLink} from '../components/BigButton';
import {Band, Screen} from '../components/Screen';
import {useI18n} from '../i18n';
import {colors, font, size} from '../theme';

type Props = {
  protectedNow: boolean;
  trustedPersonName: string | null;
  onOpenSettings: () => void;
  onOpenDev: () => void;
};

export function HomeScreen({protectedNow, trustedPersonName, onOpenSettings, onOpenDev}: Props): React.JSX.Element {
  const {t} = useI18n();
  const tone = protectedNow ? 'plain' : 'amber';
  const onBand = protectedNow ? null : styles.onColor;
  return (
    <Screen top={tone} testID="home-screen">
      <Band tone={tone} style={protectedNow ? null : styles.bandDown}>
        <Pressable onLongPress={onOpenDev} delayLongPress={2000} testID="app-title" accessibilityRole="text">
          <Text style={[styles.appName, onBand]}>{t('appName')}</Text>
        </Pressable>
        <View
          accessibilityRole="summary"
          accessibilityLiveRegion="polite"
          testID={protectedNow ? 'status-protected' : 'status-unavailable'}
          style={styles.status}>
          <Text style={[styles.title, protectedNow ? styles.ok : styles.onColor]} accessibilityRole="header">
            {protectedNow ? t('protectedTitle') : t('unavailableTitle')}
          </Text>
          <Text style={[styles.text, onBand]}>{protectedNow ? t('protectedText') : t('unavailableText')}</Text>
        </View>
      </Band>

      <View style={styles.spacer} />

      <View style={styles.footer}>
        <Text style={styles.trusted} testID="home-trusted">
          {trustedPersonName ? t('trustedPersonLine', {name: trustedPersonName}) : t('noTrustedPerson')}
        </Text>
        <TextLink label={t('settings')} onPress={onOpenSettings} testID="open-settings" />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  bandDown: {paddingBottom: 48},
  appName: {fontSize: font.small, color: colors.muted},
  status: {marginTop: 72},
  title: {fontSize: font.huge, lineHeight: 56, fontWeight: '700', color: colors.ink},
  ok: {color: colors.green},
  onColor: {color: colors.onColor},
  text: {fontSize: font.body, lineHeight: 36, color: colors.ink, marginTop: 20, maxWidth: 520},
  spacer: {flex: 1},
  footer: {paddingHorizontal: size.side, paddingBottom: 24},
  trusted: {fontSize: font.small, lineHeight: 32, color: colors.muted},
});
