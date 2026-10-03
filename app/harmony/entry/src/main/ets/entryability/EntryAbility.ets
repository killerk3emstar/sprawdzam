/**
 * Copyright (c) 2025 Huawei Technologies Co., Ltd.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */

import { RNAbility } from '@rnoh/react-native-openharmony';
import { AbilityConstant, Want } from '@kit.AbilityKit';
import { window } from '@kit.ArkUI';
import { runAudioSpike } from '../callengine/AudioSpike';

function wantsAudioSpike(want: Want): boolean {
  return want.parameters !== undefined && want.parameters['spike'] === 'audio';
}

export default class EntryAbility extends RNAbility {
  private audioSpikeRequested: boolean = false;

  override getPagePath() {
    return 'pages/Index';
  }

  override getRNOHWorkerScriptUrl() {
    return "entry/ets/workers/RNOHWorker.ets"
  }

  override onCreate(want: Want, launchParam?: AbilityConstant.LaunchParam) {
    super.onCreate(want, launchParam);
    this.audioSpikeRequested = wantsAudioSpike(want);
  }

  override onWindowStageCreate(windowStage: window.WindowStage) {
    super.onWindowStageCreate(windowStage);
    if (this.audioSpikeRequested) {
      // Debug-only hook: `aa start ... --ps spike audio` (see callengine/AudioSpike.ets).
      setTimeout(() => {
        runAudioSpike(this.context);
      }, 1500);
    }
  }

  override onNewWant(want: Want, launchParam: AbilityConstant.LaunchParam): void {
    super.onNewWant(want, launchParam);
    if (wantsAudioSpike(want)) {
      runAudioSpike(this.context);
    }
  }
}
