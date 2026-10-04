package pl.sprawdzam.app.callengine

import android.Manifest
import android.app.Activity
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.telephony.SmsManager
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * Sends the backend's `alert_trusted` text to the trusted person as an SMS from the senior's own phone
 * (docs/APP_PROTOCOL_EXTENSIONS.md). The result comes from the radio's "sent" broadcast (one per message
 * part), so `sent=true` means the network accepted every part, not just that the call to SmsManager returned.
 *
 * At most one SMS per callId (the backend may resend after a reconnect). The number and text are never logged.
 */
class TrustedSms(private val context: Context) {
  data class Result(val callId: String, val sent: Boolean, val error: String?)

  private val main = Handler(Looper.getMainLooper())
  private val handled = LinkedHashSet<String>()
  private var nextRequest = 0

  fun hasPermission(): Boolean =
      ContextCompat.checkSelfPermission(context, Manifest.permission.SEND_SMS) == PackageManager.PERMISSION_GRANTED

  /**
   * Sends [text] to [number] once per [callId]; [onResult] runs on the main thread exactly once.
   * Returns false (and does not call [onResult]) for a duplicate callId.
   */
  fun send(callId: String, number: String?, text: String, onResult: (Result) -> Unit): Boolean {
    synchronized(handled) {
      if (!handled.add(callId)) return false
      while (handled.size > MAX_REMEMBERED) handled.remove(handled.first())
    }
    val done = once(onResult)
    when {
      number.isNullOrBlank() -> done(Result(callId, false, ERR_NO_NUMBER))
      !hasPermission() -> done(Result(callId, false, ERR_NO_PERMISSION))
      text.isBlank() -> done(Result(callId, false, ERR_SEND_FAILED))
      else -> sendNow(callId, number, text, done)
    }
    return true
  }

  private fun sendNow(callId: String, number: String, text: String, done: (Result) -> Unit) {
    val sms: SmsManager? =
        if (Build.VERSION.SDK_INT >= 31) context.getSystemService(SmsManager::class.java)
        else @Suppress("DEPRECATION") SmsManager.getDefault()
    if (sms == null) {
      done(Result(callId, false, ERR_SEND_FAILED))
      return
    }
    val parts = runCatching { sms.divideMessage(text) }.getOrNull()?.takeIf { it.isNotEmpty() } ?: arrayListOf(text)
    val action = "pl.sprawdzam.app.SMS_SENT.${callId.hashCode()}.${nextRequest++}"
    var pending = parts.size
    var failed = false
    lateinit var receiver: BroadcastReceiver
    val timeout = Runnable {
      runCatching { context.unregisterReceiver(receiver) }
      Log.w(TAG, "sms: no sent confirmation within ${TIMEOUT_MS / 1000} s")
      done(Result(callId, false, ERR_SEND_FAILED))
    }
    receiver = object : BroadcastReceiver() {
      override fun onReceive(c: Context, intent: Intent) {
        if (resultCode != Activity.RESULT_OK) {
          failed = true
          Log.w(TAG, "sms: part failed (resultCode=$resultCode)")
        }
        pending--
        if (pending > 0) return
        main.removeCallbacks(timeout)
        runCatching { context.unregisterReceiver(this) }
        Log.i(TAG, "sms: ${if (failed) "failed" else "sent"} (${parts.size} part(s))")
        done(Result(callId, !failed, if (failed) ERR_SEND_FAILED else null))
      }
    }
    ContextCompat.registerReceiver(context, receiver, IntentFilter(action), ContextCompat.RECEIVER_NOT_EXPORTED)
    val sentIntents = ArrayList<PendingIntent>()
    for (i in parts.indices) {
      val intent = Intent(action).setPackage(context.packageName)
      sentIntents += PendingIntent.getBroadcast(
          context, i, intent, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_ONE_SHOT)
    }
    main.postDelayed(timeout, TIMEOUT_MS)
    try {
      if (parts.size == 1) {
        sms.sendTextMessage(number, null, parts[0], sentIntents[0], null)
      } else {
        sms.sendMultipartTextMessage(number, null, parts, sentIntents, null)
      }
      Log.i(TAG, "sms: sending ${parts.size} part(s)")
    } catch (e: Exception) {
      main.removeCallbacks(timeout)
      runCatching { context.unregisterReceiver(receiver) }
      Log.w(TAG, "sms: send threw ${e.javaClass.simpleName}")
      done(Result(callId, false, if (e is SecurityException) ERR_NO_PERMISSION else ERR_SEND_FAILED))
    }
  }

  private fun once(onResult: (Result) -> Unit): (Result) -> Unit {
    var called = false
    return { r ->
      main.post {
        if (!called) {
          called = true
          onResult(r)
        }
      }
    }
  }

  companion object {
    private const val TAG = "CallEngine"
    private const val TIMEOUT_MS = 60_000L
    private const val MAX_REMEMBERED = 50
    const val ERR_NO_PERMISSION = "no_permission"
    const val ERR_NO_NUMBER = "no_number"
    const val ERR_SEND_FAILED = "send_failed"
  }
}
