/**
 * Home: one big protection status (green / amber) and a single button to settings.
 * Long-press the app name for 2 s to open the developer panel.
 *
 * @format
 */

import React from 'react';
import {Pressable, SafeAreaView, StatusBar, StyleSheet, Text, View} from 'react-native';
import {BigButton} from '../components/BigButton';
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
  return (
    <SafeAreaView style={styles.root}>
      <View style={styles.inner}>
      <StatusBar barStyle="dark-content" backgroundColor={colors.background} />
      <Pressable onLongPress={onOpenDev} delayLongPress={2000} accessibilityRole="header" testID="app-title">
        <Text style={styles.appName}>{t('appName')}</Text>
      </Pressable>

      <View
        style={[styles.status, protectedNow ? styles.ok : styles.down]}
        accessibilityRole="summary"
        accessibilityLiveRegion="polite"
        testID={protectedNow ? 'status-protected' : 'status-unavailable'}>
        <Text style={[styles.icon, {color: protectedNow ? colors.onGreen : colors.onAmber}]}>
          {protectedNow ? '✓' : '!'}
        </Text>
        <Text style={[styles.title, {color: protectedNow ? colors.onGreen : colors.onAmber}]}>
          {protectedNow ? t('protectedTitle') : t('unavailableTitle')}
        </Text>
        <Text style={[styles.text, {color: protectedNow ? colors.onGreen : colors.onAmber}]}>
          {protectedNow ? t('protectedText') : t('unavailableText')}
        </Text>
      </View>

      {trustedPersonName ? (
        <Text style={styles.trusted}>
          {t('trustedPerson')}: {trustedPersonName}
        </Text>
      ) : null}

      <View style={styles.footer}>
        <BigButton label={t('settings')} onPress={onOpenSettings} variant="neutral" testID="open-settings" />
      </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: colors.background},
  inner: {flex: 1, paddingHorizontal: size.padding},
  appName: {fontSize: font.title, fontWeight: '800', color: colors.primary, marginTop: 24, textAlign: 'center'},
  status: {flex: 1, marginTop: 24, borderRadius: 28, padding: 28, alignItems: 'center', justifyContent: 'center'},
  ok: {backgroundColor: colors.green},
  down: {backgroundColor: colors.amber},
  icon: {fontSize: 96, fontWeight: '800', lineHeight: 110},
  title: {fontSize: font.huge, fontWeight: '800', textAlign: 'center', marginTop: 8},
  text: {fontSize: font.body, textAlign: 'center', marginTop: 16, lineHeight: 34},
  trusted: {fontSize: font.body, color: colors.muted, textAlign: 'center', marginTop: 16},
  footer: {paddingVertical: 24},
});
