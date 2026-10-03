/**
 * Call state for the senior UI, driven by CallEngine events.
 * Phases: idle -> ringing (incoming_call) -> connecting (answer tapped) -> active -> ended -> idle.
 */
import {useCallback, useEffect, useRef, useState} from 'react';
import {
  CallEngine,
  isCallEngineAvailable,
  type ProtectionStatus,
  type RiskUpdate,
} from './native/CallEngine';

export type CallPhase = 'idle' | 'ringing' | 'connecting' | 'active' | 'ended';

export type CallView = {
  phase: CallPhase;
  callId: string | null;
  caller: string;
  activeSince: number | null;
  risk: RiskUpdate | null;
  passwordRequested: boolean;
  passwordSent: boolean;
  endReason: string | null;
  error: string | null;
};

export const IDLE_CALL: CallView = {
  phase: 'idle',
  callId: null,
  caller: '',
  activeSince: null,
  risk: null,
  passwordRequested: false,
  passwordSent: false,
  endReason: null,
  error: null,
};

export type CallEngineState = {
  available: boolean;
  protection: ProtectionStatus | null;
  call: CallView;
  accept: () => void;
  reject: () => void;
  hangup: () => void;
  sendPassword: (digits: string) => void;
  enterPasswordAgain: () => void;
  dismissEnded: () => void;
};

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export function useCallEngine(controlUrl: string, deviceToken: string): CallEngineState {
  const available = isCallEngineAvailable();
  const [protection, setProtection] = useState<ProtectionStatus | null>(null);
  const [call, setCall] = useState<CallView>(IDLE_CALL);
  const callRef = useRef(call);
  callRef.current = call;

  useEffect(() => {
    if (!available) {
      return;
    }
    const subs = [
      CallEngine.addListener('protectionStatus', setProtection),
      CallEngine.addListener('incomingCall', c =>
        setCall({...IDLE_CALL, phase: 'ringing', callId: c.callId, caller: c.caller}),
      ),
      CallEngine.addListener('callActive', c =>
        setCall(prev => (prev.callId === c.callId ? {...prev, phase: 'active', activeSince: Date.now()} : prev)),
      ),
      CallEngine.addListener('risk', r => setCall(prev => (prev.callId === r.callId ? {...prev, risk: r} : prev))),
      CallEngine.addListener('verifyPassword', v =>
        setCall(prev =>
          prev.callId === v.callId ? {...prev, passwordRequested: true, passwordSent: false} : prev,
        ),
      ),
      CallEngine.addListener('callEnded', e =>
        setCall(prev => {
          if (prev.callId !== e.callId) {
            return prev;
          }
          // Declining a ringing call needs no summary screen.
          if (prev.phase === 'ringing' && e.reason === 'senior_hangup') {
            return IDLE_CALL;
          }
          return {...prev, phase: 'ended', endReason: e.reason};
        }),
      ),
    ];
    return () => subs.forEach(s => s.remove());
  }, [available]);

  useEffect(() => {
    if (!available) {
      return;
    }
    CallEngine.connectControl(controlUrl, deviceToken).catch(() => {
      // Invalid URL: the status stays "unavailable"; the settings screen shows the URL to fix.
    });
  }, [available, controlUrl, deviceToken]);

  const accept = useCallback(() => {
    const callId = callRef.current.callId;
    if (!callId || callRef.current.phase !== 'ringing') {
      return;
    }
    setCall(prev => ({...prev, phase: 'connecting', error: null}));
    CallEngine.acceptCall(callId).catch(e =>
      setCall(prev => (prev.callId === callId && prev.phase === 'connecting' ? {...prev, phase: 'ringing', error: message(e)} : prev)),
    );
  }, []);

  const hangup = useCallback(() => {
    CallEngine.hangup().catch(() => {});
  }, []);

  const sendPassword = useCallback((digits: string) => {
    CallEngine.sendDtmf(digits).then(
      () => setCall(prev => ({...prev, passwordSent: true, error: null})),
      e => setCall(prev => ({...prev, error: message(e)})),
    );
  }, []);

  const enterPasswordAgain = useCallback(() => setCall(prev => ({...prev, passwordSent: false})), []);

  const dismissEnded = useCallback(() => setCall(IDLE_CALL), []);

  return {
    available,
    protection,
    call,
    accept,
    reject: hangup,
    hangup,
    sendPassword,
    enterPasswordAgain,
    dismissEnded,
  };
}
