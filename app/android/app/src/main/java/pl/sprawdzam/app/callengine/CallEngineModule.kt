package pl.sprawdzam.app.callengine

import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import pl.sprawdzam.app.specs.NativeCallEngineSpec

/**
 * Android side of the CallEngine TurboModule (spec: app/src/native/NativeCallEngine.ts).
 *
 * Stub for now: every command rejects with "not implemented". The HarmonyOS implementation lives in
 * harmony/entry/src/main/ets/callengine. The Android version will use AudioRecord/AudioTrack and
 * OkHttp WebSockets with the same protocol v0.
 */
class CallEngineModule(reactContext: ReactApplicationContext) : NativeCallEngineSpec(reactContext) {

  override fun getName(): String = NAME

  override fun connectControl(url: String, deviceToken: String, promise: Promise) = notImplemented(promise)

  override fun disconnectControl(promise: Promise) = notImplemented(promise)

  override fun requestMicrophonePermission(promise: Promise) = notImplemented(promise)

  override fun acceptCall(callUrl: String, promise: Promise) = notImplemented(promise)

  override fun hangup(promise: Promise) = notImplemented(promise)

  override fun sendDtmf(digits: String, promise: Promise) = notImplemented(promise)

  private fun notImplemented(promise: Promise) {
    promise.reject(ERROR_NOT_IMPLEMENTED, "CallEngine is not implemented on Android yet")
  }

  companion object {
    const val NAME = NativeCallEngineSpec.NAME
    const val ERROR_NOT_IMPLEMENTED = "E_NOT_IMPLEMENTED"
  }
}
