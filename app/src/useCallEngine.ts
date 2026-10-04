/**
 * Call state for the senior UI, driven by CallEngine events.
 * Phases: idle -> ringing (incoming_call) -> connecting (answer tapped) -> active -> ended -> idle.
 */
import {useCallback, useEffect, useRef, useState} from 'react';
import {
  CallEngine,
  DEFAULT_CONFIRM_BLOCK_S,
  DEFAULT_PASSWORD_TIMEOUT_S,
  isCallEngineAvailable,
  type ProtectionStatus,
  type RiskUpdate,
  type TrustedAlert,
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
  /** Epoch ms when the backend stops waiting for the family password (verify_password.timeoutSeconds). */
  passwordDeadline: number | null;
  /** Epoch ms when the backend ends the call (confirm_block, no family password configured). */
  blockDeadline: number | null;
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
  passwordDeadline: null,
  blockDeadline: null,
  endReason: null,
  error: null,
};

export type CallEngineState = {
  available: boolean;
  protection: ProtectionStatus | null;
  call: CallView;
  /** Latest SMS-to-trusted-person result (may arrive before or after call_ended). */
  trustedAlert: TrustedAlert | null;
  accept: () => void;
  reject: () => void;
  hangup: () => void;
  sendPassword: (digits: string) => void;
  enterPasswordAgain: () => void;
  dismissEnded: () => void;
};

function seconds(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) && value > 0 ? Math.min(value, 120) : fallback;
}

function message(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

export function useCallEngine(controlUrl: string, deviceToken: string): CallEngineState {
  const available = isCallEngineAvailable();
  const [protection, setProtection] = useState<ProtectionStatus | null>(null);
  const [call, setCall] = useState<CallView>(IDLE_CALL);
  const [trustedAlert, setTrustedAlert] = useState<TrustedAlert | null>(null);
  const callRef = useRef(call);
  callRef.current = call;

  useEffect(() => {
    if (!available) {
      return;
    }
    const subs = [
      CallEngine.addListener('protectionStatus', setProtection),
      CallEngine.addListener('trustedAlert', setTrustedAlert),
      CallEngine.addListener('incomingCall', c =>
        setCall({...IDLE_CALL, phase: 'ringing', callId: c.callId, caller: c.caller}),
      ),
      CallEngine.addListener('callActive', c =>
        setCall(prev => (prev.callId === c.callId ? {...prev, phase: 'active', activeSince: Date.now()} : prev)),
      ),
      CallEngine.addListener('risk', r => setCall(prev => (prev.callId === r.callId ? {...prev, risk: r} : prev))),
      CallEngine.addListener('verifyPassword', v =>
        setCall(prev =>
          prev.callId === v.callId
            ? {
                ...prev,
                passwordRequested: true,
                passwordSent: false,
                passwordDeadline: Date.now() + seconds(v.timeoutSeconds, DEFAULT_PASSWORD_TIMEOUT_S) * 1000,
              }
            : prev,
        ),
      ),
      CallEngine.addListener('confirmBlock', b =>
        setCall(prev =>
          prev.callId === b.callId && prev.blockDeadline === null
            ? {...prev, blockDeadline: Date.now() + seconds(b.seconds, DEFAULT_CONFIRM_BLOCK_S) * 1000}
            : prev,
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
          // Hanging up from the "this looks like a scam" screen is a blocked scam even if the backend's
          // call_ended(scam_blocked) did not arrive within the hang-up grace period.
          const reason = prev.blockDeadline !== null && e.reason === 'senior_hangup' ? 'scam_blocked' : e.reason;
          return {...prev, phase: 'ended', endReason: reason};
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
    trustedAlert,
    accept,
    reject: hangup,
    hangup,
    sendPassword,
    enterPasswordAgain,
    dismissEnded,
  };
}
