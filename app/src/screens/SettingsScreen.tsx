/**
 * Settings: language (UI and calls), trusted person, notifications, and developer fields
 * (backend URL, device token, test panel).
 *
 * @format
 */

import React, {useState} from 'react';
import {ScrollView, StyleSheet, Text, TextInput, View} from 'react-native';
import {BigButton, TextLink} from '../components/BigButton';
import {Screen} from '../components/Screen';
import {useI18n, type Lang} from '../i18n';
import {toControlUrl} from '../deepLink';
import type {Settings} from '../settings';
import {colors, font, size} from '../theme';

type Props = {
  settings: Settings;
  notificationsEnabled: boolean | null;
  whitelistCount: number | null;
  /** Android: SEND_SMS granted; null where SMS is not supported. */
  smsAllowed: boolean | null;
  onAllowSms: () => void;
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
  const [devOpen, setDevOpen] = useState(false);

  const setLang = (lang: Lang) => onChange({...settings, lang});

  return (
    <Screen testID="settings-screen">
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.title} accessibilityRole="header">
          {t('settings')}
        </Text>

        <Text style={styles.section}>{t('language')}</Text>
        <View style={styles.row}>
          <BigButton
            label="Polski"
            onPress={() => setLang('pl')}
            variant={settings.lang === 'pl' ? 'primary' : 'quiet'}
            accessibilityHint={settings.lang === 'pl' ? t('on') : undefined}
            style={styles.flex}
            testID="lang-pl"
          />
          <BigButton
            label="English"
            onPress={() => setLang('en')}
            variant={settings.lang === 'en' ? 'primary' : 'quiet'}
            accessibilityHint={settings.lang === 'en' ? t('on') : undefined}
            style={styles.flex}
            testID="lang-en"
          />
        </View>

        <Text style={styles.section}>{t('trustedPerson')}</Text>
        <Text style={styles.value} testID="trusted-person">
          {settings.trustedPerson ? `${settings.trustedPerson.name}\n${settings.trustedPerson.number}` : t('notChosen')}
        </Text>
        {props.onPickTrustedPerson ? (
          <BigButton label={t('chooseFromContacts')} onPress={props.onPickTrustedPerson} variant="quiet" />
        ) : null}
        {props.smsAllowed === true ? (
          <Text style={[styles.value, styles.spaced]} testID="sms-permission-on">
            {t('smsPermissionOn')}
          </Text>
        ) : props.smsAllowed === false ? (
          <BigButton
            label={t('smsPermissionOff')}
            onPress={props.onAllowSms}
            variant="quiet"
            style={styles.spaced}
            testID="allow-sms"
          />
        ) : null}

        <Text style={styles.section}>{t('whitelist')}</Text>
        {whitelistCount !== null ? (
          <Text style={styles.value}>{t('whitelistCount', {n: whitelistCount})}</Text>
        ) : null}
        {props.onSyncContacts ? (
          <BigButton label={t('syncContacts')} onPress={props.onSyncContacts} variant="quiet" />
        ) : null}

        <Text style={styles.section}>{t('notifications')}</Text>
        {notificationsEnabled ? (
          <Text style={styles.value}>{t('notificationsOn')}</Text>
        ) : (
          <BigButton label={t('enableNotifications')} onPress={props.onEnableNotifications} variant="quiet" />
        )}

        <View style={styles.devToggle}>
          <TextLink label={t('developer')} onPress={() => setDevOpen(o => !o)} testID="toggle-dev" />
        </View>
        {devOpen ? (
          <>
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
            // A pasted tunnel address (https://x.trycloudflare.com) becomes wss://x.trycloudflare.com/app/control.
            const controlUrl = toControlUrl(url) ?? url.trim();
            setUrl(controlUrl);
            onChange({...settings, controlUrl, deviceToken: token.trim()});
            setSaved(true);
          }}
          variant="quiet"
          style={styles.spaced}
        />
        <Text style={styles.label}>{t('systemCallUi')}</Text>
        <BigButton
          label={settings.systemCallUi ? t('on') : t('off')}
          onPress={() => onChange({...settings, systemCallUi: !settings.systemCallUi})}
          variant={settings.systemCallUi ? 'primary' : 'quiet'}
          testID="toggle-system-call-ui"
        />
        <BigButton label={t('devPanel')} onPress={props.onOpenDev} variant="quiet" style={styles.spaced} />
          </>
        ) : null}
      </ScrollView>
      <View style={styles.footer}>
        <BigButton label={t('back')} onPress={onBack} testID="settings-back" />
      </View>
    </Screen>
  );
}

const styles = StyleSheet.create({
  content: {paddingHorizontal: size.side, paddingBottom: 32},
  title: {fontSize: font.title, lineHeight: 50, fontWeight: '700', color: colors.ink, marginTop: 28},
  section: {fontSize: font.body, fontWeight: '700', color: colors.ink, marginTop: 40, marginBottom: 12},
  row: {flexDirection: 'row', gap: size.gap},
  flex: {flex: 1},
  value: {fontSize: font.small, color: colors.muted, marginBottom: 12, lineHeight: 32},
  label: {fontSize: font.small, color: colors.muted, marginTop: 12, marginBottom: 6},
  input: {
    minHeight: 64,
    borderWidth: 2,
    borderColor: colors.muted,
    borderRadius: size.radius,
    paddingHorizontal: 14,
    fontSize: font.small,
    color: colors.ink,
  },
  spaced: {marginTop: 16},
  devToggle: {marginTop: 40},
  footer: {paddingHorizontal: size.side, paddingTop: 8, paddingBottom: 24},
});
