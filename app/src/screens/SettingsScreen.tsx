/**
 * Settings: language (UI and calls), trusted person, notifications, and developer fields
 * (backend URL, device token, test panel).
 *
 * @format
 */

import React, {useState} from 'react';
import {SafeAreaView, ScrollView, StatusBar, StyleSheet, Text, TextInput, View} from 'react-native';
import {BigButton} from '../components/BigButton';
import {useI18n, type Lang} from '../i18n';
import type {Settings} from '../settings';
import {colors, font, size} from '../theme';

type Props = {
  settings: Settings;
  notificationsEnabled: boolean | null;
  whitelistCount: number | null;
  onChange: (next: Settings) => void;
  onPickTrustedPerson: (() => void) | null;
  onSyncContacts: (() => void) | null;
  onEnableNotifications: () => void;
  onOpenDev: () => void;
  onBack: () => void;
};

export function SettingsScreen(props: Props): React.JSX.Element {
  const {settings, notificationsEnabled, whitelistCount, onChange, onBack} = props;
  const {t} = useI18n();
  const [url, setUrl] = useState(settings.controlUrl);
  const [token, setToken] = useState(settings.deviceToken);
  const [saved, setSaved] = useState(false);

  const setLang = (lang: Lang) => onChange({...settings, lang});

  return (
    <SafeAreaView style={styles.root} testID="settings-screen">
      <StatusBar barStyle="dark-content" backgroundColor={colors.background} />
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.title} accessibilityRole="header">
          {t('settings')}
        </Text>

        <Text style={styles.section}>{t('language')}</Text>
        <View style={styles.row}>
          <BigButton
            label="Polski"
            onPress={() => setLang('pl')}
            variant={settings.lang === 'pl' ? 'primary' : 'neutral'}
            style={styles.flex}
            testID="lang-pl"
          />
          <BigButton
            label="English"
            onPress={() => setLang('en')}
            variant={settings.lang === 'en' ? 'primary' : 'neutral'}
            style={styles.flex}
            testID="lang-en"
          />
        </View>

        <Text style={styles.section}>{t('trustedPerson')}</Text>
        <Text style={styles.value} testID="trusted-person">
          {settings.trustedPerson ? `${settings.trustedPerson.name}\n${settings.trustedPerson.number}` : t('notChosen')}
        </Text>
        {props.onPickTrustedPerson ? (
          <BigButton label={t('chooseFromContacts')} onPress={props.onPickTrustedPerson} variant="neutral" />
        ) : null}

        <Text style={styles.section}>{t('whitelist')}</Text>
        {whitelistCount !== null ? (
          <Text style={styles.value}>{t('whitelistCount', {n: whitelistCount})}</Text>
        ) : null}
        {props.onSyncContacts ? (
          <BigButton label={t('syncContacts')} onPress={props.onSyncContacts} variant="neutral" />
        ) : null}

        <Text style={styles.section}>{t('notifications')}</Text>
        {notificationsEnabled ? (
          <Text style={styles.value}>{t('notificationsOn')}</Text>
        ) : (
          <BigButton label={t('enableNotifications')} onPress={props.onEnableNotifications} variant="neutral" />
        )}

        <Text style={styles.section}>{t('developer')}</Text>
        <Text style={styles.label}>{t('backendUrl')}</Text>
        <TextInput
          style={styles.input}
          value={url}
          onChangeText={v => {
            setUrl(v);
            setSaved(false);
          }}
          autoCapitalize="none"
          autoCorrect={false}
          accessibilityLabel={t('backendUrl')}
        />
        <Text style={styles.label}>{t('deviceToken')}</Text>
        <TextInput
          style={styles.input}
          value={token}
          onChangeText={v => {
            setToken(v);
            setSaved(false);
          }}
          autoCapitalize="none"
          autoCorrect={false}
          secureTextEntry
          accessibilityLabel={t('deviceToken')}
        />
        <BigButton
          label={saved ? t('saved') : t('saveAndConnect')}
          onPress={() => {
            onChange({...settings, controlUrl: url.trim(), deviceToken: token.trim()});
            setSaved(true);
          }}
          variant="neutral"
          style={styles.spaced}
        />
        <BigButton label={t('devPanel')} onPress={props.onOpenDev} variant="neutral" style={styles.spaced} />
      </ScrollView>
      <View style={styles.footer}>
        <BigButton label={t('back')} onPress={onBack} testID="settings-back" />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {flex: 1, backgroundColor: colors.background},
  content: {paddingHorizontal: size.padding, paddingBottom: 24},
  title: {fontSize: font.title, fontWeight: '800', color: colors.text, marginTop: 24},
  section: {fontSize: font.large, fontWeight: '800', color: colors.text, marginTop: 28, marginBottom: 12},
  row: {flexDirection: 'row', gap: size.gap},
  flex: {flex: 1},
  value: {fontSize: font.body, color: colors.muted, marginBottom: 12, lineHeight: 34},
  label: {fontSize: font.body, color: colors.muted, marginTop: 8, marginBottom: 6},
  input: {
    minHeight: 64,
    borderWidth: 2,
    borderColor: colors.border,
    borderRadius: 14,
    paddingHorizontal: 14,
    fontSize: font.body,
    color: colors.text,
  },
  spaced: {marginTop: 16},
  footer: {paddingHorizontal: size.padding, paddingVertical: 16},
});
