/**
 * TurboModule spec for the native call engine.
 *
 * The audio path (WebSocket PCM frames <-> AudioCapturer/AudioRenderer) stays native;
 * JS only sends control commands and receives control events (see CallEngine.ts).
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
  /** Opens the call WebSocket, sends `accept` and starts capture/playback. */
  acceptCall(callUrl: string): Promise<void>;
  /** Sends `hangup`, closes the call WebSocket and stops audio. */
  hangup(): Promise<void>;
  /** Sends DTMF digits typed by the user (e.g. the family password). */
  sendDtmf(digits: string): Promise<void>;
}

export default TurboModuleRegistry.get<Spec>('CallEngine');
