/**
 * SEND_SMS runtime permission (Android only) for the SMS to the trusted person (alert_trusted).
 * Uses React Native's PermissionsAndroid so the CallEngine TurboModule spec (shared with HarmonyOS) stays as is.
 */
import {PermissionsAndroid, Platform} from 'react-native';

export const smsSupported = Platform.OS === 'android';

export async function hasSmsPermission(): Promise<boolean> {
  if (!smsSupported) {
    return false;
  }
  try {
    return await PermissionsAndroid.check(PermissionsAndroid.PERMISSIONS.SEND_SMS);
  } catch {
    return false;
  }
}

export async function requestSmsPermission(): Promise<boolean> {
  if (!smsSupported) {
    return false;
  }
  try {
    const result = await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.SEND_SMS);
    return result === PermissionsAndroid.RESULTS.GRANTED;
  } catch {
    return false;
  }
}
