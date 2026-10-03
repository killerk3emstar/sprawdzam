/**
 * TurboModule spec for the native call engine.
 *
 * The audio path (WebSocket PCM frames <-> AudioCapturer/AudioRenderer) stays native;
 * JS only sends control commands and receives control events (see CallEngine.ts).
 * Protocol: docs/APP_PROTOCOL.md in the server repository (v0).
 * Codegen (react-native codegen-harmony, v1) reads this file via package.json "harmony.codegenConfig".
 */
import type {TurboModule} from 'react-native';
import {TurboModuleRegistry} from 'react-native';

export interface Spec extends TurboModule {
  /** Opens the control WebSocket (`<url>?device_token=<token>`), keeps it alive and reconnects. */
  connectControl(url: string, deviceToken: string): Promise<void>;
  /** Closes the control WebSocket and stops reconnecting. */
  disconnectControl(): Promise<void>;
  /** Asks for the microphone runtime permission. Resolves true when granted. */
  requestMicrophonePermission(): Promise<boolean>;
  /**
   * Answers the ringing call (its call channel is already open since incoming_call):
   * sends `accept` and starts capture/playback.
   */
  acceptCall(callId: string): Promise<void>;
  /** Ends the active call or rejects the ringing one (`hangup`); callEnded follows. */
  hangup(): Promise<void>;
  /** Sends keypad digits (0-9, *, #; 1-32 characters), e.g. the family password. */
  sendDtmf(digits: string): Promise<void>;
  /** Shows the system dialog to allow notifications if needed. Resolves true when enabled. */
  requestNotificationPermission(): Promise<boolean>;
  /** Returns the stored settings as JSON ("{}" when nothing is stored). */
  loadSettings(): Promise<string>;
  /** Stores the settings JSON (the device token goes to secure storage natively). */
  saveSettings(json: string): Promise<void>;
}

export default TurboModuleRegistry.get<Spec>('CallEngine');
