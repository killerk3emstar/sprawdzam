package pl.sprawdzam.app.callengine

import android.Manifest
import android.app.Activity
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.provider.ContactsContract
import android.util.Log
import androidx.core.content.ContextCompat
import com.facebook.react.bridge.ActivityEventListener
import com.facebook.react.bridge.Arguments
import com.facebook.react.bridge.Promise
import com.facebook.react.bridge.ReactApplicationContext
import com.facebook.react.bridge.WritableMap
import com.facebook.react.modules.core.PermissionAwareActivity
import java.util.concurrent.TimeUnit
import okhttp3.OkHttpClient
import org.json.JSONObject
import pl.sprawdzam.app.specs.NativeCallEngineSpec

/**
 * Android side of the CallEngine TurboModule (spec: app/src/native/NativeCallEngine.ts), with the same
 * protocol, events and behaviour as the HarmonyOS ArkTS implementation:
 * OkHttp WebSockets (control + call), AudioRecord/AudioTrack in VOICE_COMMUNICATION mode with 20 ms frames,
 * NotificationManager notifications, contact picker (ACTION_PICK, no READ_CONTACTS permission).
 * Audio and the one-time call token never reach JS.
 */
class CallEngineModule(reactContext: ReactApplicationContext) :
    NativeCallEngineSpec(reactContext), ControlChannel.Listener, CallSession.Listener, ActivityEventListener {

  private val client = OkHttpClient.Builder().readTimeout(0, TimeUnit.MILLISECONDS).build()
  private val control = ControlChannel(client, this)
  private val settings = SettingsStore(reactContext)
  private val notifier = CallNotifier(reactContext).apply { lang = settings.lang() }
  @Volatile private var call: CallSession? = null
  private var pendingPick: Promise? = null
  private var pendingPickIsWhitelist = false

  init {
    reactContext.addActivityEventListener(this)
  }

  override fun getName(): String = NAME

  // --- Spec (JS -> native) ---

  override fun connectControl(url: String, deviceToken: String, promise: Promise) {
    if (!url.startsWith("ws://") && !url.startsWith("wss://")) {
      promise.reject("E_URL", "control url must start with ws:// or wss://")
      return
    }
    control.connect(url, deviceToken)
    promise.resolve(null)
  }

  override fun disconnectControl(promise: Promise) {
    control.disconnect()
    promise.resolve(null)
  }

  override fun requestMicrophonePermission(promise: Promise) =
      requestPermission(Manifest.permission.RECORD_AUDIO, REQ_MIC) { promise.resolve(it) }

  override fun acceptCall(callId: String, promise: Promise) {
    val session = call
    if (session == null || session.callId != callId || session.state != CallSession.State.RINGING) {
      promise.reject("E_NO_CALL", "no ringing call $callId")
      return
    }
    requestPermission(Manifest.permission.RECORD_AUDIO, REQ_MIC) { ok ->
      if (!ok) {
        promise.reject("E_MIC", "microphone permission denied")
        return@requestPermission
      }
      try {
        session.accept()
        emit(Protocol.EVENT_CALL_ACTIVE, Arguments.createMap().apply { putString("callId", session.callId) })
        promise.resolve(null)
      } catch (e: Exception) {
        promise.reject("E_ACCEPT", e.message)
      }
    }
  }

  override fun hangup(promise: Promise) {
    call?.hangup()
    promise.resolve(null)
  }

  override fun sendDtmf(digits: String, promise: Promise) {
    val session = call
    if (session == null || session.state != CallSession.State.ACTIVE) {
      promise.reject("E_NO_CALL", "no active call")
      return
    }
    try {
      session.sendDtmf(digits)
      promise.resolve(null)
    } catch (e: IllegalArgumentException) {
      promise.reject("E_DTMF", e.message)
    }
  }

  override fun requestNotificationPermission(promise: Promise) {
    if (Build.VERSION.SDK_INT < 33) {
      promise.resolve(true)
      return
    }
    requestPermission(Manifest.permission.POST_NOTIFICATIONS, REQ_NOTIFICATIONS) { promise.resolve(it) }
  }

  override fun loadSettings(promise: Promise) = promise.resolve(settings.load())

  override fun saveSettings(json: String, promise: Promise) {
    try {
      settings.save(json)
      notifier.lang = settings.lang()
      sendSettingsToBackend()
      promise.resolve(null)
    } catch (e: Exception) {
      promise.reject("E_SETTINGS", e.message)
    }
  }

  override fun pickTrustedPerson(promise: Promise) = startContactPicker(promise, whitelist = false)

  /** Android has no standard multi-select picker: each pick adds one contact's number to the whitelist. */
  override fun pickWhitelistContacts(promise: Promise) = startContactPicker(promise, whitelist = true)

  override fun getWhitelistCount(promise: Promise) = promise.resolve(settings.whitelist().size.toDouble())

  // --- Control channel ---

  override fun onControlOpen() = sendSettingsToBackend()

  override fun onIncomingCall(callId: String, caller: String, lang: String, callUrl: String) {
    val current = call
    if (current != null && current.state != CallSession.State.ENDED) {
      Log.w(TAG, "ignoring incoming call: another call in progress")
      return
    }
    val session = CallSession(callId, callUrl, client, this)
    call = session
    notifier.incomingCall(caller)
    emit(Protocol.EVENT_INCOMING_CALL, Arguments.createMap().apply {
      putString("callId", callId)
      putString("caller", caller)
      putString("lang", lang)
    })
    session.connect()
  }

  override fun onProtectionStatus(available: Boolean, connected: Boolean) =
      emit(Protocol.EVENT_PROTECTION_STATUS, Arguments.createMap().apply {
        putBoolean("available", available)
        putBoolean("connected", connected)
      })

  // --- Call session ---

  override fun onRinging(callId: String) = Unit

  override fun onRisk(callId: String, score: Int, level: String, scamType: String, reasons: List<String>) {
    notifier.risk(level)
    emit(Protocol.EVENT_RISK, Arguments.createMap().apply {
      putString("callId", callId)
      putInt("score", score)
      putString("level", level)
      putString("scamType", scamType)
      putArray("reasons", Arguments.fromList(reasons))
    })
  }

  override fun onVerifyPassword(callId: String) =
      emit(Protocol.EVENT_VERIFY_PASSWORD, Arguments.createMap().apply { putString("callId", callId) })

  override fun onCallEnded(callId: String, reason: String) {
    notifier.callEnded(reason)
    emit(Protocol.EVENT_CALL_ENDED, Arguments.createMap().apply {
      putString("callId", callId)
      putString("reason", reason)
    })
  }

  override fun onError(code: String, message: String) {
    Log.w(TAG, "error $code: $message")
    emit(Protocol.EVENT_ERROR, Arguments.createMap().apply {
      putString("code", code)
      putString("message", message)
    })
  }

  // --- Contact picker (ACTION_PICK grants access to the picked contact only; no READ_CONTACTS) ---

  private fun startContactPicker(promise: Promise, whitelist: Boolean) {
    val activity = reactApplicationContext.currentActivity
    if (activity == null) {
      promise.reject("E_NO_ACTIVITY", "no foreground activity")
      return
    }
    pendingPick?.reject("E_CANCELLED", "replaced by a new pick")
    pendingPick = promise
    pendingPickIsWhitelist = whitelist
    val intent = Intent(Intent.ACTION_PICK, ContactsContract.CommonDataKinds.Phone.CONTENT_URI)
    activity.startActivityForResult(intent, REQ_PICK_CONTACT)
  }

  override fun onActivityResult(activity: Activity, requestCode: Int, resultCode: Int, data: Intent?) {
    if (requestCode != REQ_PICK_CONTACT) return
    val promise = pendingPick ?: return
    pendingPick = null
    val whitelist = pendingPickIsWhitelist
    val uri = data?.data
    val picked = if (resultCode == Activity.RESULT_OK && uri != null) readPicked(uri) else null
    when {
      whitelist && picked != null -> {
        val size = settings.addToWhitelist(listOf(picked.second))
        sendSettingsToBackend()
        promise.resolve(size.toDouble())
      }
      whitelist -> promise.resolve(settings.whitelist().size.toDouble())
      picked != null ->
          promise.resolve(JSONObject().put("name", picked.first).put("number", picked.second).toString())
      else -> promise.resolve("")
    }
  }

  private fun readPicked(uri: android.net.Uri): Pair<String, String>? {
    val projection = arrayOf(
        ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME, ContactsContract.CommonDataKinds.Phone.NUMBER)
    return runCatching {
      reactApplicationContext.contentResolver.query(uri, projection, null, null, null)?.use { c ->
        if (!c.moveToFirst()) return@use null
        val number = Protocol.normalizeNumber(c.getString(1) ?: "")
        if (number.length < 6) return@use null
        Pair((c.getString(0) ?: "").ifEmpty { number }, number)
      }
    }.getOrNull()
  }

  override fun onNewIntent(intent: Intent) = Unit

  // --- helpers ---

  private fun sendSettingsToBackend() {
    if (control.sendText(settings.settingsMessage())) {
      Log.i(TAG, "control: settings sent (whitelist ${settings.whitelist().size} numbers)")
    }
  }

  private fun granted(permission: String) =
      ContextCompat.checkSelfPermission(reactApplicationContext, permission) == PackageManager.PERMISSION_GRANTED

  private fun requestPermission(permission: String, requestCode: Int, onResult: (Boolean) -> Unit) {
    if (granted(permission)) {
      onResult(true)
      return
    }
    val activity = reactApplicationContext.currentActivity as? PermissionAwareActivity
    if (activity == null) {
      onResult(false)
      return
    }
    activity.requestPermissions(arrayOf(permission), requestCode) { code, _, results ->
      if (code == requestCode) {
        onResult(results.isNotEmpty() && results[0] == PackageManager.PERMISSION_GRANTED)
        true
      } else {
        false
      }
    }
  }

  private fun emit(event: String, payload: WritableMap) = reactApplicationContext.emitDeviceEvent(event, payload)

  override fun invalidate() {
    control.disconnect()
    call?.hangup()
    reactApplicationContext.removeActivityEventListener(this)
    super.invalidate()
  }

  companion object {
    const val NAME = NativeCallEngineSpec.NAME
    private const val TAG = "CallEngine"
    private const val REQ_MIC = 7101
    private const val REQ_NOTIFICATIONS = 7102
    private const val REQ_PICK_CONTACT = 7103
  }
}
