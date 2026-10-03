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
 */
class CallNotifier(private val context: Context) {
  private var riskShown = "none"
  var lang = "pl"

  init {
    if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
      val channel = NotificationChannel(CHANNEL_ID, "Calls and alerts", NotificationManager.IMPORTANCE_HIGH)
      channel.description = "Protected calls and scam alerts"
      context.getSystemService(NotificationManager::class.java).createNotificationChannel(channel)
    }
  }

  fun canPost(): Boolean =
      Build.VERSION.SDK_INT < 33 ||
          ContextCompat.checkSelfPermission(context, Manifest.permission.POST_NOTIFICATIONS) ==
              PackageManager.PERMISSION_GRANTED

  fun incomingCall(caller: String) {
    riskShown = "none"
    publish(ID_INCOMING, t("Połączenie chronione", "Protected call"), t("Dzwoni: ", "Caller: ") + caller)
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

  private fun publish(id: Int, title: String, text: String) {
    if (!canPost()) return
    val open = context.packageManager.getLaunchIntentForPackage(context.packageName)
        ?.addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP)
    val pending = open?.let {
      PendingIntent.getActivity(context, 0, it, PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
    }
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
    private const val CHANNEL_ID = "calls"
    private const val ID_INCOMING = 1001
    private const val ID_RISK = 1002
    private const val ID_RESULT = 1003
  }
}
