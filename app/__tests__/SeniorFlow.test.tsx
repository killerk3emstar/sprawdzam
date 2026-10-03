/**
 * End-to-end UI flow with the native module mocked: incoming call -> answer -> risk -> family password
 * on the app keypad -> blocked scam summary -> home.
 *
 * @format
 */

import React from 'react';
import {DeviceEventEmitter} from 'react-native';
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

beforeEach(() => jest.clearAllMocks());

test('senior flow from incoming call to blocked scam', async () => {
  let r!: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    r = ReactTestRenderer.create(<App />);
  });
  expect(native.connectControl).toHaveBeenCalledWith('ws://localhost:8765/app/control', 'dev-device-1-sprawdzam');

  await emit(EV.protectionStatus, {available: true, connected: true});
  expect(text(r)).toContain('You are protected');

  await emit(EV.incomingCall, {callId: 'c1', caller: '+48 *** *** 123', lang: 'en'});
  expect(text(r)).toContain('Incoming call');
  expect(text(r)).toContain('+48 *** *** 123');

  await press(r, 'accept-call');
  expect(native.acceptCall).toHaveBeenCalledWith('c1');
  await emit(EV.callActive, {callId: 'c1'});
  expect(r.root.findAllByProps({testID: 'incall-screen'}).length).toBeGreaterThan(0);

  await emit(EV.risk, {callId: 'c1', score: 64, level: 'warn', scamType: 'police', reasons: ['authority', 'money']});
  expect(text(r)).toContain('Warning: this call may be a scam');
  expect(text(r)).toContain('claims to be police or a bank');

  await emit(EV.risk, {callId: 'c1', score: 93, level: 'high', scamType: 'police', reasons: ['secrecy']});
  expect(r.root.findAllByProps({testID: 'risk-banner-high'}).length).toBeGreaterThan(0);

  await emit(EV.verifyPassword, {callId: 'c1'});
  expect(text(r)).toContain('Ask the caller for the family password');
  for (const d of ['1', '2', '3', '4']) {
    await press(r, `key-${d}`);
  }
  await press(r, 'key-Send');
  expect(native.sendDtmf).toHaveBeenCalledWith('1234');
  expect(text(r)).toContain('Password sent');

  await emit(EV.callEnded, {callId: 'c1', reason: 'scam_blocked'});
  expect(text(r)).toContain('We ended a suspicious call');
  expect(text(r)).toContain('Your trusted person has been informed.');

  await press(r, 'ended-ok');
  expect(text(r)).toContain('You are protected');
});

test('declining a ringing call returns straight to home', async () => {
  let r!: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    r = ReactTestRenderer.create(<App />);
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
    r = ReactTestRenderer.create(<App />);
  });
  await emit(EV.protectionStatus, {available: true, connected: true});
  await emit(EV.protectionStatus, {available: false, connected: false});
  expect(r.root.findAllByProps({testID: 'status-unavailable'}).length).toBeGreaterThan(0);
});

test('settings: trusted person from the contact picker is saved, whitelist count shown', async () => {
  let r!: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    r = ReactTestRenderer.create(<App />);
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
