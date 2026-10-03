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

export default class EntryAbility extends RNAbility {
  private pendingAudioSpike: AudioSpikeOptions | null = null;

  override getPagePath() {
    return 'pages/Index';
  }

  override getRNOHWorkerScriptUrl() {
    return "entry/ets/workers/RNOHWorker.ets"
  }

  override onCreate(want: Want, launchParam?: AbilityConstant.LaunchParam) {
    super.onCreate(want, launchParam);
    this.pendingAudioSpike = audioSpikeOptionsFromWant(want);
  }

  override onWindowStageCreate(windowStage: window.WindowStage) {
    super.onWindowStageCreate(windowStage);
    const opts = this.pendingAudioSpike;
    this.pendingAudioSpike = null;
    if (opts !== null) {
      // Debug-only hook: `aa start ... --ps spike audio` (see callengine/AudioSpike.ets).
      setTimeout(() => {
        runAudioSpike(this.context, opts);
      }, 1500);
    }
  }

  override onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    super.onNewWant(want, launchParam);
    const opts = audioSpikeOptionsFromWant(want);
    if (opts !== null) {
      runAudioSpike(this.context, opts);
    }
  }
}
