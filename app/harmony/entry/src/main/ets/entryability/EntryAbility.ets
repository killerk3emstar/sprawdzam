/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */

import { RNAbility } from '@rnoh/react-native-openharmony';
import { AbilityConstant, Want } from '@kit.AbilityKit';
import { window } from '@kit.ArkUI';
import { AudioSpikeOptions, audioSpikeOptionsFromWant, runAudioSpike } from '../callengine/AudioSpike';
import { CallSpikeOptions, callSpikeOptionsFromWant, runCallSpike } from '../callengine/CallSpike';
import { runVoipSpike, voipSpikeOptionsFromWant } from '../callengine/VoipSpike';

// Debug-only launch hooks (see callengine/AudioSpike.ets and callengine/CallSpike.ets):
//   aa start ... --ps spike audio|beep|call|voip
export default class EntryAbility extends RNAbility {
  private pendingAudioSpike: AudioSpikeOptions | null = null;
  private pendingCallSpike: CallSpikeOptions | null = null;
  private spikeLaunchWant: Want = {};

  override getPagePath() {
    return 'pages/Index';
  }

  override getRNOHWorkerScriptUrl() {
    return "entry/ets/workers/RNOHWorker.ets"
  }

  override onCreate(want: Want, launchParam?: AbilityConstant.LaunchParam) {
    super.onCreate(want, launchParam);
    this.pendingAudioSpike = audioSpikeOptionsFromWant(want);
    this.pendingCallSpike = callSpikeOptionsFromWant(want);
    this.spikeLaunchWant = want;
  }

  override onWindowStageCreate(windowStage: window.WindowStage) {
    super.onWindowStageCreate(windowStage);
    const opts = this.pendingAudioSpike;
    this.pendingAudioSpike = null;
    if (opts !== null) {
      setTimeout(() => {
        runAudioSpike(this.context, opts);
      }, 1500);
    }
    const voipOpts = voipSpikeOptionsFromWant(this.spikeLaunchWant);
    if (voipOpts !== null) {
      setTimeout(() => {
        runVoipSpike(voipOpts);
      }, 1500);
    }
    const callOpts = this.pendingCallSpike;
    this.pendingCallSpike = null;
    if (callOpts !== null) {
      setTimeout(() => {
        runCallSpike(callOpts);
      }, 1500);
    }
  }

  override onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    super.onNewWant(want, launchParam);
    const opts = audioSpikeOptionsFromWant(want);
    if (opts !== null) {
      runAudioSpike(this.context, opts);
    }
    const callOpts = callSpikeOptionsFromWant(want);
    if (callOpts !== null) {
      runCallSpike(callOpts);
    }
    const voipOpts = voipSpikeOptionsFromWant(want);
    if (voipOpts !== null) {
      runVoipSpike(voipOpts);
    }
  }
}
