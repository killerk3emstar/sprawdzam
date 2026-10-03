/**
 * @format
 */

import React from 'react';
import {DeviceEventEmitter} from 'react-native';
import ReactTestRenderer from 'react-test-renderer';

import {CALL_ENGINE_EVENT_NAMES, CallEngine, isCallEngineAvailable} from '../src/native/CallEngine';
import {DevCallPanel} from '../src/DevCallPanel';

// jest.mock is hoisted above the imports, so the mock object is created inside the factory.
jest.mock('../src/native/NativeCallEngine', () => ({
  __esModule: true,
  default: {
    connectControl: jest.fn(() => Promise.resolve()),
    disconnectControl: jest.fn(() => Promise.resolve()),
    requestMicrophonePermission: jest.fn(() => Promise.resolve(true)),
    acceptCall: jest.fn(() => Promise.resolve()),
    hangup: jest.fn(() => Promise.resolve()),
    sendDtmf: jest.fn(() => Promise.resolve()),
  },
}));

const mockNative = jest.requireMock('../src/native/NativeCallEngine').default;

const INCOMING = {
  callId: 'c1',
  token: 't1',
  caller: '+48 600 000 000',
  lang: 'pl',
  callUrl: 'ws://127.0.0.1:8000/app/call/c1?token=t1',
};

function text(renderer: ReactTestRenderer.ReactTestRenderer): string {
  return JSON.stringify(renderer.toJSON());
}

describe('CallEngine facade', () => {
  it('reports the native module as available', () => {
    expect(isCallEngineAvailable()).toBe(true);
  });

  it('forwards commands to the native module', async () => {
    await CallEngine.connectControl('ws://h/app/control', 'dev');
    await CallEngine.sendDtmf('1234');
    expect(mockNative.connectControl).toHaveBeenCalledWith('ws://h/app/control', 'dev');
    expect(mockNative.sendDtmf).toHaveBeenCalledWith('1234');
  });

  it('delivers native events to typed listeners and stops after remove()', () => {
    const listener = jest.fn();
    const sub = CallEngine.addListener('risk', listener);
    const risk = {score: 88, level: 'high', scamType: 'police', reasons: ['money']};
    DeviceEventEmitter.emit(CALL_ENGINE_EVENT_NAMES.risk, risk);
    sub.remove();
    DeviceEventEmitter.emit(CALL_ENGINE_EVENT_NAMES.risk, risk);
    expect(listener).toHaveBeenCalledTimes(1);
    expect(listener).toHaveBeenCalledWith(risk);
  });
});

describe('DevCallPanel', () => {
  it('shows an incoming call, risk updates and clears the call when it ends', async () => {
    let renderer!: ReactTestRenderer.ReactTestRenderer;
    await ReactTestRenderer.act(() => {
      renderer = ReactTestRenderer.create(<DevCallPanel />);
    });

    await ReactTestRenderer.act(() => {
      DeviceEventEmitter.emit(CALL_ENGINE_EVENT_NAMES.protectionStatus, {available: true, connected: true});
      DeviceEventEmitter.emit(CALL_ENGINE_EVENT_NAMES.incomingCall, INCOMING);
    });
    expect(text(renderer)).toContain('Protection active');
    expect(text(renderer)).toContain('+48 600 000 000');
    expect(text(renderer)).toContain('Accept');

    await ReactTestRenderer.act(() => {
      DeviceEventEmitter.emit(CALL_ENGINE_EVENT_NAMES.risk, {
        score: 62,
        level: 'warn',
        scamType: 'grandchild',
        reasons: ['asks for money'],
      });
      DeviceEventEmitter.emit(CALL_ENGINE_EVENT_NAMES.verifyPassword, {callId: 'c1'});
    });
    expect(text(renderer)).toContain('warn');
    expect(text(renderer)).toContain('Family password');

    await ReactTestRenderer.act(() => {
      DeviceEventEmitter.emit(CALL_ENGINE_EVENT_NAMES.callEnded, {callId: 'c1', reason: 'remote_hangup'});
    });
    // The call card is gone (the event log still mentions the caller).
    expect(text(renderer)).not.toContain('Incoming call');
    expect(text(renderer)).not.toContain('Family password');
    expect(text(renderer)).toContain('call ended: remote_hangup');
  });

  it('reports fail-open state when the control connection drops', async () => {
    let renderer!: ReactTestRenderer.ReactTestRenderer;
    await ReactTestRenderer.act(() => {
      renderer = ReactTestRenderer.create(<DevCallPanel />);
    });
    await ReactTestRenderer.act(() => {
      DeviceEventEmitter.emit(CALL_ENGINE_EVENT_NAMES.protectionStatus, {available: false, connected: false});
    });
    expect(text(renderer)).toContain('Protection temporarily unavailable');
  });
});
