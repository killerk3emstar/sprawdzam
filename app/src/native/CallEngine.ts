/**
 * JS facade over the CallEngine TurboModule.
 *
 * Commands go to the native module (ArkTS on HarmonyOS, Kotlin stub on Android).
 * Events arrive through DeviceEventEmitter, emitted natively as `CallEngine.<name>`.
 * Audio and the one-time call token never pass through JS.
 * Protocol: docs/APP_PROTOCOL.md in the server repository (v0).
 */
import {DeviceEventEmitter, EmitterSubscription} from 'react-native';
import NativeCallEngine, {type Spec} from './NativeCallEngine';

export type IncomingCall = {
  callId: string;
  /** Masked number for display only; "unknown" when the number is hidden. */
  caller: string;
  lang: 'pl' | 'en' | string;
};

export type CallActive = {callId: string};

export type RiskLevel = 'none' | 'warn' | 'high';
export type ScamType = 'none' | 'grandchild' | 'police' | 'bank' | 'other';
export type RiskReason = 'money' | 'secrecy' | 'authority' | 'urgency';

export type RiskUpdate = {
  callId: string;
  /** 0-100, smoothed by the backend. */
  score: number;
  level: RiskLevel | string;
  scamType: ScamType | string;
  reasons: (RiskReason | string)[];
};

export type VerifyPasswordRequest = {callId: string};

export type CallEndReason = 'caller_hangup' | 'senior_hangup' | 'scam_blocked' | 'timeout' | 'error';

export type CallEnded = {callId: string; reason: CallEndReason | string};

export type ProtectionStatus = {
  /** Backend reports that protection works. */
  available: boolean;
  /** Control connection is up. When false, calls pass through unprotected (fail-open). */
  connected: boolean;
};

export type CallEngineError = {code: string; message: string};

export type CallEngineEvents = {
  incomingCall: IncomingCall;
  callActive: CallActive;
  risk: RiskUpdate;
  verifyPassword: VerifyPasswordRequest;
  callEnded: CallEnded;
  protectionStatus: ProtectionStatus;
  error: CallEngineError;
};

export const CALL_ENGINE_EVENT_NAMES: {[K in keyof CallEngineEvents]: string} = {
  incomingCall: 'CallEngine.onIncomingCall',
  callActive: 'CallEngine.onCallActive',
  risk: 'CallEngine.onRisk',
  verifyPassword: 'CallEngine.onVerifyPassword',
  callEnded: 'CallEngine.onCallEnded',
  protectionStatus: 'CallEngine.onProtectionStatus',
  error: 'CallEngine.onError',
};

export function isCallEngineAvailable(): boolean {
  return NativeCallEngine != null;
}

function native(): Spec {
  if (NativeCallEngine == null) {
    throw new Error('CallEngine native module is not available on this platform');
  }
  return NativeCallEngine;
}

export const CallEngine = {
  connectControl(url: string, deviceToken: string): Promise<void> {
    return native().connectControl(url, deviceToken);
  },
  disconnectControl(): Promise<void> {
    return native().disconnectControl();
  },
  requestMicrophonePermission(): Promise<boolean> {
    return native().requestMicrophonePermission();
  },
  acceptCall(callId: string): Promise<void> {
    return native().acceptCall(callId);
  },
  hangup(): Promise<void> {
    return native().hangup();
  },
  sendDtmf(digits: string): Promise<void> {
    return native().sendDtmf(digits);
  },
  addListener<K extends keyof CallEngineEvents>(
    event: K,
    listener: (payload: CallEngineEvents[K]) => void,
  ): EmitterSubscription {
    return DeviceEventEmitter.addListener(CALL_ENGINE_EVENT_NAMES[event], listener);
  },
};
