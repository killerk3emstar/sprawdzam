package pl.sprawdzam.app.callengine

import android.os.Handler
import android.os.Looper
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import okio.ByteString.Companion.toByteString
import org.json.JSONArray
import org.json.JSONObject

/**
 * One protected call (APP_PROTOCOL.md section 2), mirroring the HarmonyOS CallSession:
 * connect() right after incoming_call (ringing) -> accept() (audio both ways) -> ended.
 */
class CallSession(
    val callId: String,
    private val url: String,
    private val client: OkHttpClient,
    private val listener: Listener,
    context: android.content.Context,
) {
  interface Listener {
    fun onRinging(callId: String)
    fun onRisk(callId: String, score: Int, level: String, scamType: String, reasons: List<String>)
    fun onVerifyPassword(callId: String, timeoutSeconds: Int)
    fun onConfirmBlock(callId: String, seconds: Int)
    fun onCallEnded(callId: String, reason: String)
    fun onError(code: String, message: String)
  }

  enum class State { CONNECTING, RINGING, ACTIVE, ENDED }

  @Volatile var state = State.CONNECTING
    private set
  private var ws: WebSocket? = null
  private val voice = VoiceAudio(context)
  private val main = Handler(Looper.getMainLooper())
  private var hangupTimer: Runnable? = null

  fun connect() {
    ws = client.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
      override fun onOpen(webSocket: WebSocket, response: Response) {
        if (state == State.CONNECTING) {
          state = State.RINGING
          Log.i(TAG, "call $callId: ringing")
          listener.onRinging(callId)
        }
      }

      override fun onMessage(webSocket: WebSocket, text: String) = onText(text)

      override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
        if (state == State.ACTIVE) voice.play(bytes.toByteArray())
      }

      override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
        webSocket.close(Protocol.CLOSE_NORMAL, null)
        onClosed(code)
      }

      override fun onClosed(webSocket: WebSocket, code: Int, reason: String) = onClosed(code)

      override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
        Log.w(TAG, "call $callId: socket failure ${t.javaClass.simpleName}")
        if (state == State.CONNECTING) listener.onError("call_channel_failed", t.message ?: "connect failed")
        finish(Protocol.REASON_ERROR)
      }
    })
  }

  fun accept() {
    check(state == State.RINGING) { "cannot accept in state $state" }
    send(JSONObject().put("type", "accept"))
    state = State.ACTIVE
    voice.start { frame -> if (state == State.ACTIVE) ws?.send(frame.toByteString()) }
    Log.i(TAG, "call $callId: active")
  }

  /** Hangs up or rejects; waits up to 2 s for call_ended(senior_hangup), then ends locally. */
  fun hangup() {
    if (state == State.ENDED) return
    if (state == State.CONNECTING) {
      finish(Protocol.REASON_SENIOR_HANGUP)
      return
    }
    send(JSONObject().put("type", "hangup"))
    if (hangupTimer == null) {
      val r = Runnable { finish(Protocol.REASON_SENIOR_HANGUP) }
      hangupTimer = r
      main.postDelayed(r, HANGUP_GRACE_MS)
    }
  }

  fun sendDtmf(digits: String) {
    require(Protocol.isValidDtmf(digits)) { "dtmf must be 1-32 characters of 0-9, * or #" }
    send(JSONObject().put("type", "dtmf").put("digits", digits))
  }

  fun setMuted(muted: Boolean) {
    voice.muted = muted
  }

  fun abort(reason: String) = finish(reason)

  private fun onText(text: String) {
    val msg = runCatching { JSONObject(text) }.getOrNull() ?: return
    when (msg.optString("type")) {
      "risk" -> {
        val reasons = msg.optJSONArray("reasons") ?: JSONArray()
        listener.onRisk(
            callId,
            msg.optInt("score", 0),
            msg.optString("level", "none"),
            msg.optString("scamType", "none"),
            List(reasons.length()) { reasons.optString(it) })
      }
      "verify_password" ->
          listener.onVerifyPassword(callId, msg.optInt("timeoutSeconds", Protocol.DEFAULT_PASSWORD_TIMEOUT_S))
      "confirm_block" -> listener.onConfirmBlock(callId, msg.optInt("seconds", Protocol.DEFAULT_CONFIRM_BLOCK_S))
      "call_ended" -> finish(msg.optString("reason", Protocol.REASON_ERROR))
      else -> Unit // unknown types are ignored (forward compatibility)
    }
  }

  private fun onClosed(code: Int) {
    if (code == Protocol.CLOSE_POLICY && state != State.ENDED) {
      listener.onError("call_auth_failed", "backend rejected the call token (1008)")
    }
    finish(Protocol.REASON_ERROR) // a close without call_ended means the channel dropped
  }

  private fun send(msg: JSONObject) {
    ws?.send(msg.toString())
  }

  @Synchronized
  private fun finish(reason: String) {
    if (state == State.ENDED) return
    val wasActive = state == State.ACTIVE
    state = State.ENDED
    hangupTimer?.let { main.removeCallbacks(it) }
    hangupTimer = null
    ws?.close(Protocol.CLOSE_NORMAL, null)
    ws = null
    if (wasActive) voice.stop()
    Log.i(TAG, "call $callId: ended ($reason) ${voice.stats}")
    listener.onCallEnded(callId, reason)
  }

  companion object {
    private const val TAG = "CallEngine"
    private const val HANGUP_GRACE_MS = 2000L
  }
}
