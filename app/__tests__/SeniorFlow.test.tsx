/**
 * End-to-end UI flow with the native module mocked: incoming call -> answer -> risk -> family password
 * on the app keypad -> blocked scam summary -> home.
 *
 * @format
 */

import React from 'react';
import {DeviceEventEmitter, Linking} from 'react-native';
import ReactTestRenderer from 'react-test-renderer';
import App from '../App';
import {CALL_ENGINE_EVENT_NAMES as EV} from '../src/native/CallEngine';

jest.mock('../src/native/NativeCallEngine', () => ({
  __esModule: true,
  default: {
    connectControl: jest.fn(() => Promise.resolve()),
    disconnectControl: jest.fn(() => Promise.resolve()),
    requestMicrophonePermission: jest.fn(() => Promise.resolve(true)),
    acceptCall: jest.fn(() => Promise.resolve()),
    hangup: jest.fn(() => Promise.resolve()),
    sendDtmf: jest.fn(() => Promise.resolve()),
    requestNotificationPermission: jest.fn(() => Promise.resolve(true)),
    loadSettings: jest.fn(() => Promise.resolve('{"lang":"en","notificationsAsked":true}')),
    saveSettings: jest.fn(() => Promise.resolve()),
    pickTrustedPerson: jest.fn(() => Promise.resolve('{"name":"Anna","number":"+48600100200"}')),
    pickWhitelistContacts: jest.fn(() => Promise.resolve(3)),
    getWhitelistCount: jest.fn(() => Promise.resolve(0)),
  },
}));

const native = jest.requireMock('../src/native/NativeCallEngine').default;

function text(r: ReactTestRenderer.ReactTestRenderer): string {
  return JSON.stringify(r.toJSON());
}

async function emit(name: string, payload: object) {
  await ReactTestRenderer.act(async () => {
    DeviceEventEmitter.emit(name, payload);
  });
}

async function press(r: ReactTestRenderer.ReactTestRenderer, testID: string) {
  await ReactTestRenderer.act(async () => {
    r.root.findByProps({testID}).props.onPress();
  });
}

const mounted: ReactTestRenderer.ReactTestRenderer[] = [];

// Every mounted App listens to the same DeviceEventEmitter, so unmount after each test.
function mount(): ReactTestRenderer.ReactTestRenderer {
  const r = ReactTestRenderer.create(<App />);
  mounted.push(r);
  return r;
}

beforeEach(() => jest.clearAllMocks());

afterEach(async () => {
  await ReactTestRenderer.act(async () => {
    mounted.splice(0).forEach(r => r.unmount());
  });
});

test('senior flow from incoming call to blocked scam', async () => {
  let r!: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    r = mount();
  });
  expect(native.connectControl).toHaveBeenCalledWith('ws://localhost:8765/app/control', 'dev-device-1-sprawdzam');

  await emit(EV.protectionStatus, {available: true, connected: true});
  expect(text(r)).toContain('You are protected');

  await emit(EV.incomingCall, {callId: 'c1', caller: '+48 *** *** 123', lang: 'en'});
  expect(text(r)).toContain('Unknown number calling');
  expect(text(r)).toContain('+48 *** *** 123');

  await press(r, 'accept-call');
  expect(native.acceptCall).toHaveBeenCalledWith('c1');
  await emit(EV.callActive, {callId: 'c1'});
  expect(r.root.findAllByProps({testID: 'incall-screen'}).length).toBeGreaterThan(0);

  await emit(EV.risk, {callId: 'c1', score: 64, level: 'warn', scamType: 'police', reasons: ['authority', 'money']});
  expect(text(r)).toContain('Warning: the caller claims to be police or a bank and asks for money.');

  await emit(EV.risk, {callId: 'c1', score: 93, level: 'high', scamType: 'police', reasons: ['secrecy']});
  expect(r.root.findAllByProps({testID: 'risk-high'}).length).toBeGreaterThan(0);
  expect(text(r)).toContain('High scam risk: the caller asks you to keep it secret.');

  // Older backends (and the frozen HarmonyOS module) send no timeoutSeconds: 12 s countdown.
  await emit(EV.verifyPassword, {callId: 'c1'});
  expect(text(r)).toContain('Ask the caller for the family password');
  expect(text(r)).toContain('12 s left');
  for (const d of ['1', '2', '3', '4']) {
    await press(r, `key-${d}`);
  }
  await press(r, 'key-Send');
  expect(native.sendDtmf).toHaveBeenCalledWith('1234');
  expect(text(r)).toContain('Password sent');

  await emit(EV.callEnded, {callId: 'c1', reason: 'scam_blocked'});
  expect(text(r)).toContain('We ended a suspicious call');
  expect(text(r)).toContain('Do not call this number back.');
  await emit(EV.trustedAlert, {callId: 'c1', sent: true, error: null, name: 'Anna'});
  expect(text(r)).toContain('Text message sent to: Anna');

  await press(r, 'ended-ok');
  expect(text(r)).toContain('You are protected');
});

test('declining a ringing call returns straight to home', async () => {
  let r!: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    r = mount();
  });
  await emit(EV.incomingCall, {callId: 'c2', caller: 'unknown', lang: 'en'});
  expect(text(r)).toContain('Hidden number');
  await press(r, 'reject-call');
  expect(native.hangup).toHaveBeenCalled();
  await emit(EV.callEnded, {callId: 'c2', reason: 'senior_hangup'});
  expect(text(r)).toContain('Protection temporarily unavailable');
});

test('the backend dropping the control channel shows the amber state', async () => {
  let r!: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    r = mount();
  });
  await emit(EV.protectionStatus, {available: true, connected: true});
  await emit(EV.protectionStatus, {available: false, connected: false});
  expect(r.root.findAllByProps({testID: 'status-unavailable'}).length).toBeGreaterThan(0);
});

test('settings: trusted person from the contact picker is saved, whitelist count shown', async () => {
  let r!: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    r = mount();
  });
  await press(r, 'open-settings');
  expect(text(r)).toContain('Not chosen');
  await ReactTestRenderer.act(async () => {
    r.root.findByProps({accessibilityLabel: 'Choose from contacts'}).props.onPress();
  });
  expect(text(r)).toContain('Anna');
  const saved = JSON.parse(native.saveSettings.mock.calls.at(-1)[0]);
  expect(saved.trustedPerson).toEqual({name: 'Anna', number: '+48600100200'});
  await ReactTestRenderer.act(async () => {
    r.root.findByProps({accessibilityLabel: 'Choose contacts'}).props.onPress();
  });
  expect(text(r)).toContain('Numbers from contacts: 3');
});

async function startActiveCall(callId: string, settingsJson: string) {
  native.loadSettings.mockImplementationOnce(() => Promise.resolve(settingsJson));
  let r!: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    r = mount();
  });
  await emit(EV.incomingCall, {callId, caller: '+48 *** *** 123', lang: 'pl'});
  await press(r, 'accept-call');
  await emit(EV.callActive, {callId});
  return r;
}

const WITH_TRUSTED = '{"lang":"pl","notificationsAsked":true,"trustedPerson":{"name":"Anna","number":"+48600100200"}}';

test('verify_password shows the countdown from timeoutSeconds', async () => {
  jest.useFakeTimers({doNotFake: ['nextTick', 'setImmediate']});
  try {
    const r = await startActiveCall('c3', WITH_TRUSTED);
    await emit(EV.verifyPassword, {callId: 'c3', timeoutSeconds: 5});
    expect(text(r)).toContain('Zostało 5 s');
    await ReactTestRenderer.act(async () => {
      jest.advanceTimersByTime(2100);
    });
    expect(text(r)).toContain('Zostało 3 s');
    await ReactTestRenderer.act(async () => {
      jest.advanceTimersByTime(4000);
    });
    expect(text(r)).toContain('Czas minął. Rozłączamy.');
  } finally {
    jest.useRealTimers();
  }
});

test('confirm_block: red countdown, "Hang up now" -> blocked screen -> call the trusted person', async () => {
  const open = jest.spyOn(Linking, 'openURL').mockImplementation(() => Promise.resolve(true));
  const r = await startActiveCall('c4', WITH_TRUSTED);
  await emit(EV.risk, {callId: 'c4', score: 95, level: 'high', scamType: 'grandchild', reasons: ['money', 'urgency']});
  expect(text(r)).toContain('Duże ryzyko oszustwa: rozmówca prosi o pieniądze i ponagla Cię.');
  await emit(EV.confirmBlock, {callId: 'c4', seconds: 8});
  expect(r.root.findAllByProps({testID: 'confirm-block-screen'}).length).toBeGreaterThan(0);
  expect(text(r)).toContain('To wygląda na oszustwo');
  expect(text(r)).toMatch(/Rozłączam za [78] s/);
  expect(text(r)).not.toContain('Kontynuuj');

  await press(r, 'block-now');
  expect(native.hangup).toHaveBeenCalledTimes(1);
  // Backend did not answer with scam_blocked in time: the local senior_hangup still shows the blocked result.
  await emit(EV.callEnded, {callId: 'c4', reason: 'senior_hangup'});
  expect(text(r)).toContain('Rozłączyliśmy podejrzaną rozmowę');
  expect(text(r)).toContain('Nie oddzwaniaj na ten numer.');
  await press(r, 'call-trusted');
  expect(open).toHaveBeenCalledWith('tel:+48600100200');
  open.mockRestore();
});

test('confirm_block hangs up locally when the backend has not ended the call after the countdown', async () => {
  jest.useFakeTimers({doNotFake: ['nextTick', 'setImmediate']});
  try {
    const r = await startActiveCall('c5', WITH_TRUSTED);
    await emit(EV.confirmBlock, {callId: 'c5', seconds: 2});
    await ReactTestRenderer.act(async () => {
      jest.advanceTimersByTime(2500);
    });
    expect(text(r)).toContain('Rozłączam…');
    expect(native.hangup).not.toHaveBeenCalled();
    await ReactTestRenderer.act(async () => {
      jest.advanceTimersByTime(3000);
    });
    expect(native.hangup).toHaveBeenCalledTimes(1);
  } finally {
    jest.useRealTimers();
  }
});

test('blocked scam without a trusted person offers no call button', async () => {
  const r = await startActiveCall('c6', '{"lang":"pl","notificationsAsked":true}');
  await emit(EV.callEnded, {callId: 'c6', reason: 'scam_blocked'});
  expect(text(r)).toContain('Rozłączyliśmy podejrzaną rozmowę');
  expect(r.root.findAllByProps({testID: 'call-trusted'}).length).toBe(0);
});
