/**
 * Developer panel that exercises the CallEngine end to end:
 * connect control socket -> incoming call -> accept -> risk updates / password prompt -> hang up.
 * Functional only; the real senior-facing screens come later.
 *
 * @format
 */

import React, {useCallback, useEffect, useState} from 'react';
import {Button, StyleSheet, Text, TextInput, View} from 'react-native';
import {
  CallEngine,
  isCallEngineAvailable,
  type IncomingCall,
  type ProtectionStatus,
  type RiskUpdate,
} from './native/CallEngine';

// Dev backend reached through `hdc rport tcp:8765 tcp:8765` (port 8000 is taken by basal-serve on the dev Mac).
// Production uses wss://.
const DEFAULT_CONTROL_URL = 'ws://127.0.0.1:8765/app/control';
const DEFAULT_DEVICE_TOKEN = 'dev-device-1';
const MAX_LOG = 8;

type CallState = 'idle' | 'ringing' | 'connecting' | 'active';

const RISK_COLORS: Record<string, string> = {
  none: '#2E7D32',
  warn: '#EF6C00',
  high: '#C62828',
};

export function DevCallPanel(): React.JSX.Element {
  const available = isCallEngineAvailable();
  const [controlUrl, setControlUrl] = useState(DEFAULT_CONTROL_URL);
  const [status, setStatus] = useState<ProtectionStatus | null>(null);
  const [incoming, setIncoming] = useState<IncomingCall | null>(null);
  const [callState, setCallState] = useState<CallState>('idle');
  const [risk, setRisk] = useState<RiskUpdate | null>(null);
  const [passwordAsked, setPasswordAsked] = useState(false);
  const [password, setPassword] = useState('');
  const [log, setLog] = useState<string[]>([]);

  const addLog = useCallback((line: string) => {
    const time = new Date().toTimeString().slice(0, 8);
    setLog(prev => [`${time} ${line}`, ...prev].slice(0, MAX_LOG));
  }, []);

  useEffect(() => {
    if (!available) {
      return;
    }
    const subs = [
      CallEngine.addListener('protectionStatus', s => {
        setStatus(s);
        addLog(`protection connected=${s.connected} available=${s.available}`);
      }),
      CallEngine.addListener('incomingCall', call => {
        setIncoming(call);
        setRisk(null);
        setPasswordAsked(false);
        setCallState('ringing');
        addLog(`incoming call ${call.callId} from ${call.caller}`);
      }),
      CallEngine.addListener('risk', r => {
        setRisk(r);
        addLog(`risk ${r.level} ${r.score}`);
      }),
      CallEngine.addListener('verifyPassword', () => {
        setPasswordAsked(true);
        addLog('verify password requested');
      }),
      CallEngine.addListener('callEnded', e => {
        setCallState('idle');
        setIncoming(null);
        setPasswordAsked(false);
        addLog(`call ended: ${e.reason}`);
      }),
      CallEngine.addListener('error', e => addLog(`error ${e.code}: ${e.message}`)),
    ];
    return () => subs.forEach(s => s.remove());
  }, [available, addLog]);

  const run = useCallback(
    (label: string, op: () => Promise<unknown>) => {
      op().then(
        () => addLog(`${label}: ok`),
        (e: unknown) => addLog(`${label} failed: ${e instanceof Error ? e.message : String(e)}`),
      );
    },
    [addLog],
  );

  if (!available) {
    return (
      <View style={styles.panel}>
        <Text style={styles.muted}>CallEngine native module is not available.</Text>
      </View>
    );
  }

  const accept = () => {
    if (!incoming) {
      return;
    }
    setCallState('connecting');
    CallEngine.acceptCall(incoming.callId).then(
      () => {
        setCallState('active');
        addLog('call active');
      },
      (e: unknown) => {
        // The call stays ringing (or ends via callEnded) on the native side.
        setCallState('ringing');
        addLog(`accept failed: ${e instanceof Error ? e.message : String(e)}`);
      },
    );
  };

  const protectionLabel =
    status === null
      ? 'Ochrona: nie połączono / Protection: not connected'
      : status.available
      ? 'Ochrona aktywna / Protection active'
      : 'Ochrona chwilowo niedostępna / Protection temporarily unavailable';

  return (
    <View style={styles.panel}>
      <Text style={styles.heading}>CallEngine (dev)</Text>
      <TextInput
        style={styles.input}
        value={controlUrl}
        onChangeText={setControlUrl}
        autoCapitalize="none"
        autoCorrect={false}
        accessibilityLabel="Control URL"
      />
      <View style={styles.row}>
        <Button
          title="Connect"
          onPress={() => run('connect', () => CallEngine.connectControl(controlUrl, DEFAULT_DEVICE_TOKEN))}
        />
        <Button title="Disconnect" onPress={() => run('disconnect', () => CallEngine.disconnectControl())} />
        <Button title="Mic" onPress={() => run('mic permission', () => CallEngine.requestMicrophonePermission())} />
      </View>
      <Text style={styles.status} testID="protection-status">
        {protectionLabel}
      </Text>

      {incoming && callState !== 'idle' ? (
        <View style={styles.call}>
          <Text style={styles.callTitle}>
            {callState === 'ringing' ? 'Połączenie przychodzące / Incoming call' : 'Rozmowa / Call'}
          </Text>
          <Text style={styles.caller}>{incoming.caller || incoming.callId}</Text>
          {risk ? (
            <Text style={[styles.risk, {color: RISK_COLORS[risk.level] ?? '#13212F'}]} testID="risk-level">
              Ryzyko / Risk: {risk.level} ({risk.score}) {risk.scamType !== 'none' ? risk.scamType : ''}
              {risk.reasons.length > 0 ? `\n${risk.reasons.join(', ')}` : ''}
            </Text>
          ) : null}
          {passwordAsked ? (
            <View style={styles.row}>
              <TextInput
                style={[styles.input, styles.password]}
                value={password}
                onChangeText={setPassword}
                keyboardType="number-pad"
                placeholder="Hasło rodzinne / Family password"
                accessibilityLabel="Family password"
              />
              <Button
                title="Send"
                onPress={() => {
                  run('dtmf', () => CallEngine.sendDtmf(password));
                  setPassword('');
                }}
              />
            </View>
          ) : null}
          <View style={styles.row}>
            {callState === 'ringing' ? <Button title="Odbierz / Accept" onPress={accept} /> : null}
            {callState === 'ringing' ? (
              <Button title="Odrzuć / Reject" color="#C62828" onPress={() => run('reject', () => CallEngine.hangup())} />
            ) : (
              <Button title="Rozłącz / Hang up" color="#C62828" onPress={() => run('hangup', () => CallEngine.hangup())} />
            )}
          </View>
        </View>
      ) : null}

      <View style={styles.log}>
        {log.map(line => (
          <Text key={line} style={styles.logLine}>
            {line}
          </Text>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  panel: {
    alignSelf: 'stretch',
    marginTop: 16,
    padding: 12,
    borderRadius: 12,
    backgroundColor: '#FFFFFF',
  },
  heading: {fontSize: 16, fontWeight: '700', color: '#13212F', marginBottom: 8},
  input: {
    borderWidth: 1,
    borderColor: '#C5CED8',
    borderRadius: 8,
    paddingHorizontal: 8,
    paddingVertical: 6,
    fontSize: 14,
    color: '#13212F',
  },
  row: {flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 8, alignItems: 'center'},
  status: {marginTop: 8, fontSize: 14, color: '#4A5A6A'},
  call: {marginTop: 12, padding: 10, borderRadius: 10, backgroundColor: '#F4F7FB'},
  callTitle: {fontSize: 16, fontWeight: '600', color: '#13212F'},
  caller: {fontSize: 20, fontWeight: '700', color: '#0B4F8A', marginTop: 4},
  risk: {marginTop: 8, fontSize: 16, fontWeight: '600'},
  password: {flex: 1, minWidth: 160},
  log: {marginTop: 12},
  logLine: {fontSize: 11, color: '#4A5A6A', fontFamily: 'monospace'},
  muted: {fontSize: 14, color: '#4A5A6A'},
});
