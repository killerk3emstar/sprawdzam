package pl.sprawdzam.app.callengine

import android.os.Handler
import android.os.Looper
import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject

/**
 * Control WebSocket (APP_PROTOCOL.md section 1), mirroring the HarmonyOS ControlChannel: ping every 15 s,
 * reconnect on any close (incl. 1008 and the 4000 idle close) with backoff 1/2/5/10 s, reset on the first
 * valid message.
 */
class ControlChannel(private val client: OkHttpClient, private val listener: Listener) {
  interface Listener {
    fun onControlOpen()
    fun onIncomingCall(callId: String, caller: String, lang: String, callUrl: String)
    fun onProtectionStatus(available: Boolean, connected: Boolean)
    /** Protocol extension `alert_trusted`: text the trusted person from this phone. */
    fun onAlertTrusted(callId: String, scamType: String, reasons: List<String>, text: String)
    fun onError(code: String, message: String)
  }

  private val main = Handler(Looper.getMainLooper())
  private var ws: WebSocket? = null
  private var url = ""
  private var fullUrl = ""
  private var wanted = false
  private var connected = false
  private var serverAvailable = false
  private var attempt = 0
  private var generation = 0
  /** Messages that must not be lost while reconnecting (e.g. alert_trusted_result), flushed on open. */
  private val outbox = ArrayDeque<String>()
  private val ping = object : Runnable {
    override fun run() {
      sendText(JSONObject().put("type", "ping").toString())
      main.postDelayed(this, PING_INTERVAL_MS)
    }
  }
  private val reconnect = Runnable { if (wanted) open() }

  fun connect(url: String, deviceToken: String) = main.post {
    disconnectNow()
    this.url = url
    val sep = if (url.contains('?')) '&' else '?'
    fullUrl = "$url${sep}device_token=${java.net.URLEncoder.encode(deviceToken, "UTF-8")}"
    wanted = true
    attempt = 0
    open()
  }

  fun disconnect() = main.post { disconnectNow() }

  /** Sends a text frame if the channel is open. */
  fun sendText(text: String): Boolean {
    val socket = ws
    if (socket == null || !connected) return false
    return socket.send(text)
  }

  /** Sends now, or queues until the next (re)connect. Main thread or any thread. */
  fun sendReliably(text: String) = main.post {
    if (!sendText(text)) {
      outbox.addLast(text)
      while (outbox.size > 20) outbox.removeFirst()
    }
  }

  private fun disconnectNow() {
    wanted = false
    main.removeCallbacks(reconnect)
    main.removeCallbacks(ping)
    closeSocket()
    setStatus(false, serverAvailable)
  }

  private fun open() {
    closeSocket()
    val gen = ++generation
    Log.i(TAG, "control: connecting to $url")
    ws = client.newWebSocket(Request.Builder().url(fullUrl).build(), object : WebSocketListener() {
      override fun onOpen(webSocket: WebSocket, response: Response) = main.post {
        if (gen != generation) return@post
        Log.i(TAG, "control: connected")
        setStatus(true, serverAvailable)
        main.removeCallbacks(ping)
        main.postDelayed(ping, PING_INTERVAL_MS)
        listener.onControlOpen()
        while (outbox.isNotEmpty() && sendText(outbox.first())) outbox.removeFirst()
      }.let {}

      override fun onMessage(webSocket: WebSocket, text: String) = main.post {
        if (gen == generation) onText(text)
      }.let {}

      override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
        webSocket.close(Protocol.CLOSE_NORMAL, null)
        main.post { if (gen == generation) lost("closed: $code", code) }
      }

      override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) = main.post {
        if (gen == generation) lost("failure: ${t.javaClass.simpleName}", -1)
      }.let {}
    })
  }

  private fun onText(text: String) {
    val msg = runCatching { JSONObject(text) }.getOrNull() ?: return
    attempt = 0
    when (msg.optString("type")) {
      "incoming_call" -> {
        val callId = msg.optString("callId")
        val token = msg.optString("token")
        if (callId.isEmpty() || token.isEmpty()) {
          listener.onError("protocol", "incoming_call without callId/token")
          return
        }
        listener.onIncomingCall(
            callId,
            msg.optString("caller", "unknown"),
            msg.optString("lang", "pl"),
            Protocol.callUrlFromControlUrl(url, callId, token))
      }
      "protection_status" -> setStatus(connected, msg.optBoolean("available", false))
      "alert_trusted" -> {
        val callId = msg.optString("callId")
        if (callId.isEmpty()) {
          listener.onError("protocol", "alert_trusted without callId")
          return
        }
        val reasons = msg.optJSONArray("reasons")
        listener.onAlertTrusted(
            callId,
            msg.optString("scamType", "other"),
            List(reasons?.length() ?: 0) { reasons!!.optString(it) },
            msg.optString("text", ""))
      }
      else -> Unit // pong and unknown types
    }
  }

  private fun lost(why: String, code: Int) {
    Log.w(TAG, "control: connection lost ($why)")
    if (code == Protocol.CLOSE_POLICY) {
      listener.onError("control_auth_failed", "backend rejected the device token (1008)")
    }
    main.removeCallbacks(ping)
    closeSocket()
    setStatus(false, false)
    if (!wanted) return
    val delay = BACKOFF_MS[minOf(attempt, BACKOFF_MS.size - 1)]
    attempt++
    main.removeCallbacks(reconnect)
    main.postDelayed(reconnect, delay)
  }

  private fun setStatus(connected: Boolean, available: Boolean) {
    if (connected == this.connected && available == serverAvailable) return
    this.connected = connected
    serverAvailable = available
    listener.onProtectionStatus(connected && available, connected)
  }

  private fun closeSocket() {
    generation++
    ws?.close(Protocol.CLOSE_NORMAL, null)
    ws = null
  }

  companion object {
    private const val TAG = "CallEngine"
    private const val PING_INTERVAL_MS = 15_000L
    private val BACKOFF_MS = longArrayOf(1000, 2000, 5000, 10_000)
  }
}
