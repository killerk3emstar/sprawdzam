package pl.sprawdzam.app.callengine

import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationManagerCompat
import androidx.core.content.ContextCompat

/**
 * Foreground service that keeps the app process (and with it the control WebSocket owned by CallEngineModule)
 * alive while the app is in the background or the screen is off. Without it Android 14+ freezes the cached
 * process within seconds and an incoming protected call would never reach the phone.
 *
 * Type `specialUse` while waiting for calls; `specialUse|microphone` during an active call so call audio keeps
 * flowing if the senior leaves the app (the microphone type can only be added while the app is in the
 * foreground, which is the case when the senior taps Answer).
 */
class ProtectionService : Service() {

  override fun onBind(intent: Intent?): IBinder? = null

  override fun onCreate() {
    super.onCreate()
    instance = this
  }

  override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
    instance = this
    promote(inCall = false)
    return START_STICKY
  }

  override fun onDestroy() {
    if (instance === this) instance = null
    super.onDestroy()
  }

  private fun promote(inCall: Boolean) {
    val notification = CallNotifier(this).apply { lang = SettingsStore(this@ProtectionService).lang() }
        .statusNotification(protectedNow)
    try {
      if (Build.VERSION.SDK_INT >= 34) {
        var type = ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
        if (inCall) type = type or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
        startForeground(CallNotifier.ID_STATUS, notification, type)
      } else {
        startForeground(CallNotifier.ID_STATUS, notification)
      }
    } catch (e: Exception) {
      // E.g. the microphone type requested from the background; the service keeps its previous type.
      Log.w(TAG, "protection service: startForeground failed: ${e.javaClass.simpleName}")
    }
  }

  companion object {
    private const val TAG = "CallEngine"
    @Volatile private var instance: ProtectionService? = null
    @Volatile private var protectedNow = false

    /** Starts the service; call while the app is in the foreground (Android 12+ restriction). */
    fun start(context: Context) {
      if (instance != null) return
      try {
        ContextCompat.startForegroundService(context, Intent(context, ProtectionService::class.java))
      } catch (e: Exception) {
        Log.w(TAG, "protection service: cannot start: ${e.javaClass.simpleName}")
      }
    }

    fun stop(context: Context) {
      context.stopService(Intent(context, ProtectionService::class.java))
    }

    /** Updates the ongoing notification text (protection on / temporarily unavailable). */
    fun setProtected(context: Context, value: Boolean, lang: String) {
      protectedNow = value
      if (instance == null) return
      val notifier = CallNotifier(context).apply { this.lang = lang }
      if (!notifier.canPost()) return
      try {
        NotificationManagerCompat.from(context).notify(CallNotifier.ID_STATUS, notifier.statusNotification(value))
      } catch (e: SecurityException) {
        // Notifications revoked.
      }
    }

    fun setInCall(inCall: Boolean) {
      instance?.promote(inCall)
    }
  }
}
