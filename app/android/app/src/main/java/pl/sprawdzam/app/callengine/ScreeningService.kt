package pl.sprawdzam.app.callengine

import android.os.Build
import android.telecom.Call
import android.telecom.CallScreeningService
import android.util.Log
import androidx.annotation.RequiresApi

/**
 * Android path from CLAUDE.md: as the call-screening app (RoleManager.ROLE_CALL_SCREENING) Sprawdzam would
 * reject calls from numbers that are not contacts; the operator's "forward when busy" then sends them to the
 * backend, and the senior answers them in the app.
 *
 * STUB: currently allows every call. Not wired to the role request yet; to activate, request the role with
 * RoleManager.createRequestRoleIntent(RoleManager.ROLE_CALL_SCREENING) and decide per call (Call.Details
 * marks numbers that are in contacts via getCallerNumberVerificationStatus / the whitelist from settings).
 */
@RequiresApi(Build.VERSION_CODES.Q)
class ScreeningService : CallScreeningService() {
  override fun onScreenCall(callDetails: Call.Details) {
    Log.i("CallEngine", "screening: incoming call (allowed, stub)")
    respondToCall(callDetails, CallResponse.Builder().build())
  }
}
