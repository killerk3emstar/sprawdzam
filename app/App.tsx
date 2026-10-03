/**
 * Sprawdzam / Second Ear: senior UI (minimal, large, high-contrast), shared by HarmonyOS (RNOH) and Android.
 *
 * Routing: an incoming or active call always takes over the screen; otherwise Home, Settings or the
 * developer panel (long-press the app name on Home for 2 s).
 *
 * @format
 */

import React, {useCallback, useEffect, useState} from 'react';
import {Pressable, SafeAreaView, ScrollView, StatusBar, StyleSheet, Text, View} from 'react-native';
import {DevCallPanel} from './src/DevCallPanel';
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
  const {call} = engine;

  const requestNotifications = useCallback(() => {
    if (!engine.available) {
      return;
    }
    CallEngine.requestNotificationPermission().then(setNotificationsEnabled, () => setNotificationsEnabled(false));
  }, [engine.available]);

  // Ask for notifications once, on the first start.
  useEffect(() => {
    if (engine.available && !settings.notificationsAsked) {
      onSettingsChange({...settings, notificationsAsked: true});
      requestNotifications();
    }
  }, [engine.available, settings, onSettingsChange, requestNotifications]);

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
      return <CallEndedScreen reason={call.endReason} onOk={engine.dismissEnded} />;
    }
  }

  if (route === 'settings') {
    return (
      <SettingsScreen
        settings={settings}
        notificationsEnabled={notificationsEnabled}
        whitelistCount={null}
        onChange={onSettingsChange}
        onPickTrustedPerson={null}
        onSyncContacts={null}
        onEnableNotifications={requestNotifications}
        onOpenDev={() => setRoute('dev')}
        onBack={() => setRoute('home')}
      />
    );
  }

  if (route === 'dev') {
    return (
      <SafeAreaView style={styles.devRoot}>
        <StatusBar barStyle="dark-content" backgroundColor={colors.surface} />
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
  splash: {flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.background},
  splashText: {fontSize: font.title, fontWeight: '800', color: colors.primary},
  devRoot: {flex: 1, backgroundColor: colors.surface},
  devContent: {padding: 16},
  devBack: {minHeight: 56, justifyContent: 'center'},
  devBackText: {fontSize: font.body, color: colors.primary, fontWeight: '700'},
});

export default App;
