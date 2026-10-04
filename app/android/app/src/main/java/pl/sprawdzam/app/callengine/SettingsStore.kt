package pl.sprawdzam.app.callengine

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

/**
 * Settings JSON (owned by JS, app/src/settings.ts) and the whitelist, in app-private SharedPreferences.
 * TODO: move the device token to the Android Keystore (EncryptedSharedPreferences) like Asset Store Kit on
 * HarmonyOS. Whitelist numbers are never logged and are sent only over the control channel.
 */
class SettingsStore(context: Context) {
  private val prefs = context.getSharedPreferences("sprawdzam_settings", Context.MODE_PRIVATE)

  fun load(): String = prefs.getString(KEY_SETTINGS, "{}") ?: "{}"

  fun save(json: String) {
    JSONObject(json) // validate
    prefs.edit().putString(KEY_SETTINGS, json).apply()
  }

  fun lang(): String = runCatching { JSONObject(load()).optString("lang", "pl") }.getOrDefault("pl")

  fun trustedPerson(): JSONObject? = runCatching {
    val tp = JSONObject(load()).optJSONObject("trustedPerson")
    if (tp != null && tp.has("number")) tp else null
  }.getOrNull()

  fun whitelist(): List<String> = runCatching {
    val arr = JSONArray(prefs.getString(KEY_WHITELIST, "[]"))
    List(arr.length()) { arr.getString(it) }
  }.getOrDefault(emptyList())

  /** Adds numbers to the whitelist (deduplicated). Returns the new size. */
  fun addToWhitelist(numbers: Collection<String>): Int {
    val all = LinkedHashSet(whitelist())
    all.addAll(numbers)
    prefs.edit().putString(KEY_WHITELIST, JSONArray(all.toList()).toString()).apply()
    return all.size
  }

  /** Protocol extension: {"type":"settings","lang","trustedPerson","whitelist"}. */
  fun settingsMessage(): String =
      JSONObject()
          .put("type", "settings")
          .put("lang", lang())
          .put("trustedPerson", trustedPerson() ?: JSONObject.NULL)
          .put("whitelist", JSONArray(whitelist()))
          .toString()

  companion object {
    private const val KEY_SETTINGS = "settings"
    private const val KEY_WHITELIST = "whitelist"
  }
}
