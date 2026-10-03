/**
 * Full-screen incoming protected call: masked caller, big Answer (green) and Decline (red).
 *
 * @format
 */

import React from 'react';
import {SafeAreaView, StatusBar, StyleSheet, Text, View} from 'react-native';
import {BigButton} from '../components/BigButton';
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
    <SafeAreaView style={styles.root} testID="incoming-screen">
      <View style={styles.inner}>
      <StatusBar barStyle="light-content" backgroundColor={colors.callBackground} />
      <View style={styles.top}>
        <Text style={styles.label}>{t('incomingTitle')}</Text>
        <Text
          style={styles.caller}
          accessibilityRole="header"
          numberOfLines={1}
          adjustsFontSizeToFit
          minimumFontScale={0.6}>
          {shown}
        </Text>
        <Text style={styles.protected}>{t('incomingProtected')}</Text>
        {error ? <Text style={styles.error}>{error}</Text> : null}
      </View>
      <View style={styles.actions}>
        <BigButton
          label={connecting ? t('connecting') : t('accept')}
          onPress={onAccept}
          variant="green"
          disabled={connecting}
          tall
          testID="accept-call"
        />
        <BigButton label={t('reject')} onPress={onReject} variant="red" tall testID="reject-call" />
      </View>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: colors.callBackground},
  inner: {flex: 1, paddingHorizontal: size.padding},
  top: {flex: 1, alignItems: 'center', justifyContent: 'center'},
  label: {fontSize: font.large, color: colors.onCallMuted},
  // 40 pt keeps a masked number ("+48 *** *** 123") on one line on a 360 dp wide phone.
  caller: {fontSize: font.title, fontWeight: '800', color: colors.onCall, marginTop: 16, textAlign: 'center'},
  protected: {fontSize: font.body, color: colors.onCallMuted, marginTop: 20, textAlign: 'center'},
  error: {fontSize: font.body, color: '#FFCDD2', marginTop: 16, textAlign: 'center'},
  actions: {gap: 20, paddingBottom: 32},
});
