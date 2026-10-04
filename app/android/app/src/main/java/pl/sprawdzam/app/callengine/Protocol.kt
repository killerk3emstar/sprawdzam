package pl.sprawdzam.app.callengine

/**
 * App <-> backend protocol v0 (server repo docs/APP_PROTOCOL.md) plus the app's `settings` extension
 * (docs/APP_PROTOCOL_EXTENSIONS.md). Same constants and rules as the HarmonyOS implementation.
 */
object Protocol {
  const val CLOSE_NORMAL = 1000
  const val CLOSE_POLICY = 1008
  const val CLOSE_IDLE = 4000

  const val REASON_SENIOR_HANGUP = "senior_hangup"
  const val REASON_ERROR = "error"

  /** Defaults when an older backend omits verify_password.timeoutSeconds / confirm_block.seconds. */
  const val DEFAULT_PASSWORD_TIMEOUT_S = 12
  const val DEFAULT_CONFIRM_BLOCK_S = 8

  const val SAMPLE_RATE = 16000
  const val FRAME_BYTES = 640 // 20 ms PCM16 mono at 16 kHz

  // Events emitted to JS through DeviceEventEmitter (same names as on HarmonyOS).
  const val EVENT_INCOMING_CALL = "CallEngine.onIncomingCall"
  const val EVENT_CALL_ACTIVE = "CallEngine.onCallActive"
  const val EVENT_RISK = "CallEngine.onRisk"
  const val EVENT_VERIFY_PASSWORD = "CallEngine.onVerifyPassword"
  /** Extension (APP_PROTOCOL_EXTENSIONS.md): no family password configured, the backend ends the call soon. */
  const val EVENT_CONFIRM_BLOCK = "CallEngine.onConfirmBlock"
  const val EVENT_CALL_ENDED = "CallEngine.onCallEnded"
  const val EVENT_PROTECTION_STATUS = "CallEngine.onProtectionStatus"
  const val EVENT_ERROR = "CallEngine.onError"
  /** Android only (protocol extension alert_trusted): result of the SMS to the trusted person. */
  const val EVENT_TRUSTED_ALERT = "CallEngine.onTrustedAlert"

  private val DTMF = Regex("^[0-9*#]{1,32}$")

  fun isValidDtmf(digits: String): Boolean = DTMF.matches(digits)

  /** ws://host:8765/app/control?device_token=x -> ws://host:8765/app/call/<callId>?token=<token> */
  fun callUrlFromControlUrl(controlUrl: String, callId: String, token: String): String {
    var base = controlUrl.substringBefore('?')
    val marker = base.indexOf("/app/control")
    base = if (marker >= 0) {
      base.substring(0, marker)
    } else {
      val schemeEnd = base.indexOf("://")
      val pathStart = if (schemeEnd >= 0) base.indexOf('/', schemeEnd + 3) else -1
      if (pathStart >= 0) base.substring(0, pathStart) else base
    }
    return "$base/app/call/${enc(callId)}?token=${enc(token)}"
  }

  /** E.164-like normalization (digits with a leading "+"; "00" -> "+"; 9 digits -> +48). */
  fun normalizeNumber(raw: String): String {
    var n = raw.replace(Regex("[^0-9+]"), "")
    if (n.startsWith("00")) n = "+" + n.substring(2)
    if (!n.startsWith("+")) {
      n = n.replace("+", "")
      if (n.length == 9) n = "+48$n" else if (n.length == 11 && n.startsWith("48")) n = "+$n"
    }
    return n
  }

  private fun enc(s: String): String = java.net.URLEncoder.encode(s, "UTF-8")
}
