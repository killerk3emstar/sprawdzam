/**
 * Sprawdzam / Second Ear: senior UI (minimal, large, high-contrast), shared by HarmonyOS (RNOH) and Android.
 *
 * Routing: an incoming or active call always takes over the screen; otherwise Home, Settings or the
 * developer panel (long-press the app name on Home for 2 s).
 *
 * @format
 */

import React, {useCallback, useEffect, useRef, useState} from 'react';
import {Linking, Pressable, SafeAreaView, ScrollView, StatusBar, StyleSheet, Text, View} from 'react-native';
import {DevCallPanel} from './src/DevCallPanel';
import {parseConfigLink} from './src/deepLink';
import {hasSmsPermission, requestSmsPermission, smsSupported} from './src/smsPermission';
import {I18nProvider} from './src/i18n';
import {CallEngine} from './src/native/CallEngine';
import {CallEndedScreen} from './src/screens/CallEndedScreen';
import {HomeScreen} from './src/screens/HomeScreen';
import {InCallScreen} from './src/screens/InCallScreen';
import {IncomingCallScreen} from './src/screens/IncomingCallScreen';
import {SettingsScreen} from './src/screens/SettingsScreen';
import {DEFAULT_SETTINGS, loadSettings, saveSettings, type Settings} from './src/settings';
import {colors, font} from './src/theme';
import {useCallEngine} from './src/useCallEngine';

type Route = 'home' | 'settings' | 'dev';

function Main({settings, onSettingsChange}: {settings: Settings; onSettingsChange: (s: Settings) => void}): React.JSX.Element {
  const engine = useCallEngine(settings.controlUrl, settings.deviceToken);
  const [route, setRoute] = useState<Route>('home');
  const [notificationsEnabled, setNotificationsEnabled] = useState<boolean | null>(null);
  const [whitelistCount, setWhitelistCount] = useState<number | null>(null);
  const [smsAllowed, setSmsAllowed] = useState<boolean | null>(null);
  const {call} = engine;

  const askSms = useCallback(() => {
    requestSmsPermission().then(setSmsAllowed);
  }, []);

  useEffect(() => {
    if (engine.available) {
      CallEngine.getWhitelistCount().then(setWhitelistCount, () => setWhitelistCount(null));
    }
  }, [engine.available]);

  const pickTrustedPerson = useCallback(() => {
    CallEngine.pickTrustedPerson().then(
      person => {
        if (person) {
          onSettingsChange({...settings, trustedPerson: person});
          askSms();
        }
      },
      () => {},
    );
  }, [settings, onSettingsChange, askSms]);

  // Opens the dialer with the number filled in (tel: is ACTION_VIEW -> dialer; no CALL_PHONE permission).
  const callTrustedPerson = useCallback((number: string) => {
    Linking.openURL(`tel:${number.replace(/[^0-9+]/g, '')}`).catch(() => {});
  }, []);

  const syncContacts = useCallback(() => {
    CallEngine.pickWhitelistContacts().then(setWhitelistCount, () => {});
  }, []);

  const requestNotifications = useCallback(() => {
    if (!engine.available) {
      return;
    }
    CallEngine.requestNotificationPermission().then(setNotificationsEnabled, () => setNotificationsEnabled(false));
  }, [engine.available]);

  // Permissions at start, one dialog after another, so nothing is asked in the middle of a call:
  // notifications (first start only), microphone (call audio), SMS (only when a trusted person is set).
  const startupAsked = useRef(false);
  useEffect(() => {
    if (!engine.available || startupAsked.current || call.phase !== 'idle') {
      return;
    }
    startupAsked.current = true;
    const first = !settings.notificationsAsked;
    if (first) {
      onSettingsChange({...settings, notificationsAsked: true});
    }
    (async () => {
      if (first) {
        setNotificationsEnabled(await CallEngine.requestNotificationPermission().catch(() => false));
      }
      await CallEngine.requestMicrophonePermission().catch(() => false);
      if (smsSupported) {
        const ok = await hasSmsPermission();
        setSmsAllowed(ok || (settings.trustedPerson ? await requestSmsPermission() : false));
      }
    })();
  }, [engine.available, call.phase, settings, onSettingsChange]);

  if (route !== 'dev') {
    if (call.phase === 'ringing' || call.phase === 'connecting') {
      return (
        <IncomingCallScreen
          caller={call.caller}
          connecting={call.phase === 'connecting'}
          error={call.error}
          onAccept={engine.accept}
          onReject={engine.reject}
        />
      );
    }
    if (call.phase === 'active') {
      return (
        <InCallScreen
          call={call}
          onHangup={engine.hangup}
          onSendPassword={engine.sendPassword}
          onEnterAgain={engine.enterPasswordAgain}
        />
      );
    }
    if (call.phase === 'ended' && call.endReason) {
      const alert = engine.trustedAlert?.callId === call.callId ? engine.trustedAlert : null;
      return (
        <CallEndedScreen
          reason={call.endReason}
          trustedAlert={alert}
          trustedPerson={settings.trustedPerson ?? null}
          onCallTrusted={callTrustedPerson}
          onOk={engine.dismissEnded}
        />
      );
    }
  }

  if (route === 'settings') {
    return (
      <SettingsScreen
        settings={settings}
        notificationsEnabled={notificationsEnabled}
        whitelistCount={whitelistCount}
        smsAllowed={smsSupported ? smsAllowed : null}
        onAllowSms={askSms}
        onChange={onSettingsChange}
        onPickTrustedPerson={engine.available ? pickTrustedPerson : null}
        onSyncContacts={engine.available ? syncContacts : null}
        onEnableNotifications={requestNotifications}
        onOpenDev={() => setRoute('dev')}
        onBack={() => setRoute('home')}
      />
    );
  }

  if (route === 'dev') {
    return (
      <SafeAreaView style={styles.devRoot}>
        <StatusBar barStyle="dark-content" backgroundColor={colors.paper} />
        <ScrollView contentContainerStyle={styles.devContent} keyboardShouldPersistTaps="handled">
          <Pressable accessibilityRole="button" onPress={() => setRoute('home')} style={styles.devBack}>
            <Text style={styles.devBackText}>← Sprawdzam</Text>
          </Pressable>
          <DevCallPanel initialUrl={settings.controlUrl} deviceToken={settings.deviceToken} />
        </ScrollView>
      </SafeAreaView>
    );
  }

  const protectedNow = !!engine.protection?.available && !!engine.protection?.connected;
  return (
    <HomeScreen
      protectedNow={protectedNow}
      trustedPersonName={settings.trustedPerson?.name ?? null}
      onOpenSettings={() => setRoute('settings')}
      onOpenDev={() => setRoute('dev')}
    />
  );
}

function App(): React.JSX.Element {
  const [settings, setSettings] = useState<Settings | null>(null);

  useEffect(() => {
    let cancelled = false;
    loadSettings().then(
      s => !cancelled && setSettings(s),
      () => !cancelled && setSettings(DEFAULT_SETTINGS),
    );
    return () => {
      cancelled = true;
    };
  }, []);

  const onSettingsChange = useCallback((next: Settings) => {
    setSettings(next);
    saveSettings(next);
  }, []);

  // Dev/demo: sprawdzam://config?url=...&token=... sets the backend address (see src/deepLink.ts).
  useEffect(() => {
    if (!settings) {
      return;
    }
    const apply = (link: string | null) => {
      const cfg = link ? parseConfigLink(link) : null;
      if (cfg) {
        setSettings(prev => {
          const next = {...(prev ?? DEFAULT_SETTINGS), ...cfg};
          saveSettings(next);
          return next;
        });
      }
    };
    Linking.getInitialURL().then(apply, () => {});
    const sub = Linking.addEventListener('url', e => apply(e.url));
    return () => sub.remove();
  }, [settings === null]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!settings) {
    return (
      <View style={styles.splash}>
        <Text style={styles.splashText}>Sprawdzam</Text>
      </View>
    );
  }

  return (
    <I18nProvider lang={settings.lang}>
      <Main settings={settings} onSettingsChange={onSettingsChange} />
    </I18nProvider>
  );
}

const styles = StyleSheet.create({
  splash: {flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.paper},
  splashText: {fontSize: font.title, fontWeight: '700', color: colors.ink},
  devRoot: {flex: 1, backgroundColor: colors.paper},
  devContent: {padding: 16},
  devBack: {minHeight: 56, justifyContent: 'center'},
  devBackText: {fontSize: font.small, color: colors.ink, textDecorationLine: 'underline'},
});

export default App;
