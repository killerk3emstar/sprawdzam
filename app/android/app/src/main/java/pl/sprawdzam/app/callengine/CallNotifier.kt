package pl.sprawdzam.app.callengine

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

/**
 * Notifications for protected calls (same cases and texts as the HarmonyOS CallNotifier): incoming call,
 * warn/high risk (once per level per call), blocked scam. Channel "calls" with high importance.
 *
 * The incoming-call notification carries a full-screen intent, so a call that arrives while the app is in
 * the background or the screen is off opens MainActivity over the lock screen (Android 14+: needs the
 * USE_FULL_SCREEN_INTENT app-op, granted by default for sideloaded apps; see [canUseFullScreenIntent]).
 * Android additionally gets a quiet "protection on/off" notification for the foreground service.
 */
class CallNotifier(private val context: Context) {
  private var riskShown = "none"
  var lang = "pl"

  init {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      val channel = NotificationChannel(CHANNEL_ID, "Calls and alerts", NotificationManager.IMPORTANCE_HIGH)
      channel.description = "Protected calls and scam alerts"
      val status = NotificationChannel(STATUS_CHANNEL_ID, "Protection status", NotificationManager.IMPORTANCE_LOW)
      status.description = "Shows that Sprawdzam is protecting calls"
      status.setShowBadge(false)
      val nm = context.getSystemService(NotificationManager::class.java)
      nm.createNotificationChannel(channel)
      nm.createNotificationChannel(status)
    }
  }

  fun canUseFullScreenIntent(): Boolean =
      Build.VERSION.SDK_INT < 34 ||
          context.getSystemService(NotificationManager::class.java).canUseFullScreenIntent()

  /** Ongoing notification of the protection foreground service. */
  fun statusNotification(protectedNow: Boolean): android.app.Notification =
      NotificationCompat.Builder(context, STATUS_CHANNEL_ID)
          .setSmallIcon(android.R.drawable.ic_lock_idle_lock)
          .setContentTitle(
              if (protectedNow) t("Sprawdzam: ochrona włączona", "Sprawdzam: protection on")
              else t("Sprawdzam: ochrona chwilowo niedostępna", "Sprawdzam: protection temporarily unavailable"))
          .setContentText(
              if (protectedNow) t("Sprawdzamy rozmowy z nieznanych numerów.", "We check calls from unknown numbers.")
              else t("Rozmowy przechodzą bez sprawdzania. Łączymy ponownie.", "Calls go through unchecked. Reconnecting."))
          .setOngoing(true)
          .setOnlyAlertOnce(true)
          .setPriority(NotificationCompat.PRIORITY_LOW)
          .setCategory(NotificationCompat.CATEGORY_SERVICE)
          .apply { openAppIntent(null)?.let { setContentIntent(it) } }
          .build()

  fun cancelIncoming() = NotificationManagerCompat.from(context).cancel(ID_INCOMING)

  fun canPost(): Boolean =
      Build.VERSION.SDK_INT < 33 ||
          ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
              PackageManager.PERMISSION_GRANTED

  fun incomingCall(caller: String) {
    riskShown = "none"
    if (!canPost()) return
    val title = t("Połączenie chronione", "Protected call")
    val text = t("Dzwoni: ", "Caller: ") + caller
    val fullScreen = openAppIntent(EXTRA_INCOMING_CALL)
    val notification = NotificationCompat.Builder(context, CHANNEL_ID)
        .setSmallIcon(android.R.drawable.sym_call_incoming)
        .setContentTitle(title)
        .setContentText(text)
        .setPriority(NotificationCompat.PRIORITY_MAX)
        .setCategory(NotificationCompat.CATEGORY_CALL)
        .setOngoing(true)
        .setTimeoutAfter(INCOMING_TIMEOUT_MS)
        .apply {
          if (fullScreen != null) {
            setContentIntent(fullScreen)
            setFullScreenIntent(fullScreen, true)
          }
        }
        .build()
    try {
      NotificationManagerCompat.from(context).notify(ID_INCOMING, notification)
    } catch (e: SecurityException) {
      // Permission revoked meanwhile.
    }
  }

  fun risk(level: String) {
    if (level != "warn" && level != "high") return
    if (level == riskShown || (level == "warn" && riskShown == "high")) return
    riskShown = level
    if (level == "high") {
      publish(
          ID_RISK,
          t("Wysokie ryzyko oszustwa", "High scam risk"),
          t("Zapytaj rozmówcę o hasło rodzinne. Nie podawaj pieniędzy ani kodów.",
              "Ask the caller for the family password. Do not give money or codes."))
    } else {
      publish(
          ID_RISK,
          t("Uwaga: możliwe oszustwo", "Warning: possible scam"),
          t("Ta rozmowa może być oszustwem. Nie podawaj pieniędzy ani kodów.",
              "This call may be a scam. Do not give money or codes."))
    }
  }

  fun callEnded(reason: String) {
    val nm = NotificationManagerCompat.from(context)
    nm.cancel(ID_INCOMING)
    nm.cancel(ID_RISK)
    if (reason == "scam_blocked") {
      publish(
          ID_RESULT,
          t("Rozłączyliśmy podejrzaną rozmowę", "We ended a suspicious call"),
          t("Powiadomiliśmy osobę zaufaną.", "Your trusted person has been informed."))
    }
  }

  private fun t(pl: String, en: String) = if (lang == "en") en else pl

  private fun openAppIntent(extra: String?): PendingIntent? {
    val open = context.packageManager.getLaunchIntentForPackage(context.packageName)
        ?.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_NEW_TASK)
        ?: return null
    if (extra != null) open.putExtra(extra, true)
    return PendingIntent.getActivity(
        context, if (extra != null) 1 else 0, open, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
  }

  private fun publish(id: Int, title: String, text: String) {
    if (!canPost()) return
    val pending = openAppIntent(null)
    val notification = NotificationCompat.Builder(context, CHANNEL_ID)
        .setSmallIcon(android.R.drawable.ic_dialog_alert)
        .setContentTitle(title)
        .setContentText(text)
        .setStyle(NotificationCompat.BigTextStyle().bigText(text))
        .setPriority(NotificationCompat.PRIORITY_HIGH)
        .setCategory(NotificationCompat.CATEGORY_CALL)
        .setAutoCancel(true)
        .apply { if (pending != null) setContentIntent(pending) }
        .build()
    try {
      NotificationManagerCompat.from(context).notify(id, notification)
    } catch (e: SecurityException) {
      // Permission revoked meanwhile.
    }
  }

  companion object {
    const val EXTRA_INCOMING_CALL = "pl.sprawdzam.app.INCOMING_CALL"
    const val ID_STATUS = 1000
    private const val CHANNEL_ID = "calls"
    private const val STATUS_CHANNEL_ID = "status"
    private const val INCOMING_TIMEOUT_MS = 90_000L
    private const val ID_INCOMING = 1001
    private const val ID_RISK = 1002
    private const val ID_RESULT = 1003
  }
}
