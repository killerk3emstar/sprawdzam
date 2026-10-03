/**
 * Sprawdzam / Second Ear: hello-world screen.
 * Shared by the HarmonyOS (RNOH) and Android builds.
 * Real screens (protection status, incoming call, alerts) come later.
 *
 * @format
 */

import React from 'react';
import {
  Platform,
  SafeAreaView,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from 'react-native';

const COLORS = {
  background: '#F4F7FB',
  card: '#FFFFFF',
  primary: '#0B4F8A',
  text: '#13212F',
  muted: '#4A5A6A',
};

function App(): React.JSX.Element {
  return (
    <SafeAreaView style={styles.root}>
      <StatusBar barStyle="dark-content" backgroundColor={COLORS.background} />
      <View style={styles.content}>
        <Text style={styles.title} accessibilityRole="header">
          Sprawdzam
        </Text>
        <Text style={styles.subtitle}>Second Ear</Text>

        <View style={styles.card}>
          <Text style={styles.line}>
            Ochrona przed oszustwami telefonicznymi
          </Text>
          <Text style={styles.line}>Protection against phone scams</Text>
        </View>

        <Text style={styles.platform} testID="platform-label">
          Platform: {Platform.OS}
        </Text>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  content: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 24,
  },
  title: {
    fontSize: 40,
    fontWeight: '700',
    color: COLORS.primary,
  },
  subtitle: {
    marginTop: 4,
    fontSize: 22,
    fontWeight: '500',
    color: COLORS.muted,
  },
  card: {
    marginTop: 32,
    paddingVertical: 20,
    paddingHorizontal: 24,
    borderRadius: 16,
    backgroundColor: COLORS.card,
    alignSelf: 'stretch',
  },
  line: {
    fontSize: 22,
    lineHeight: 30,
    color: COLORS.text,
    textAlign: 'center',
    marginVertical: 6,
  },
  platform: {
    marginTop: 24,
    fontSize: 16,
    color: COLORS.muted,
  },
});

export default App;
