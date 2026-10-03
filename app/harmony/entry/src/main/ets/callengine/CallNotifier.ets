/**
 * System notifications (Notification Kit) for protected calls, so the senior notices them even when the app
 * is in the background: incoming call, warn/high risk (once per level per call), and a blocked scam.
 * Tapping a notification opens the app. Texts follow the app language (PL/EN).
 */
import { notificationManager } from '@kit.NotificationKit';
import { common, Want, wantAgent, WantAgent } from '@kit.AbilityKit';
import { BusinessError } from '@kit.BasicServicesKit';
import { hilog } from '@kit.PerformanceAnalysisKit';

const DOMAIN: number = 0x5350;
const TAG: string = 'CallEngine';
const ID_INCOMING: number = 1001;
const ID_RISK: number = 1002;
const ID_RESULT: number = 1003;

interface Texts {
  incomingTitle: string;
  incomingText: string;
  warnTitle: string;
  warnText: string;
  highTitle: string;
  highText: string;
  blockedTitle: string;
  blockedText: string;
}

const PL: Texts = {
  incomingTitle: 'Połączenie chronione',
  incomingText: 'Dzwoni: ',
  warnTitle: 'Uwaga: możliwe oszustwo',
  warnText: 'Ta rozmowa może być oszustwem. Nie podawaj pieniędzy ani kodów.',
  highTitle: 'Wysokie ryzyko oszustwa',
  highText: 'Zapytaj rozmówcę o hasło rodzinne. Nie podawaj pieniędzy ani kodów.',
  blockedTitle: 'Rozłączyliśmy podejrzaną rozmowę',
  blockedText: 'Powiadomiliśmy osobę zaufaną.'
};

const EN: Texts = {
  incomingTitle: 'Protected call',
  incomingText: 'Caller: ',
  warnTitle: 'Warning: possible scam',
  warnText: 'This call may be a scam. Do not give money or codes.',
  highTitle: 'High scam risk',
  highText: 'Ask the caller for the family password. Do not give money or codes.',
  blockedTitle: 'We ended a suspicious call',
  blockedText: 'Your trusted person has been informed.'
};

export class CallNotifier {
  private context: common.UIAbilityContext;
  private lang: string = 'pl';
  private riskLevelShown: string = 'none';
  private openApp: WantAgent | null = null;

  constructor(context: common.UIAbilityContext) {
    this.context = context;
  }

  setLanguage(lang: string): void {
    this.lang = lang === 'en' ? 'en' : 'pl';
  }

  /** Shows the system "allow notifications" dialog if needed. Resolves with the final state. */
  async requestPermission(): Promise<boolean> {
    try {
      if (notificationManager.isNotificationEnabledSync()) {
        return true;
      }
      await notificationManager.requestEnableNotification(this.context);
    } catch (e) {
      const err = e as BusinessError;
      hilog.warn(DOMAIN, TAG, 'notifications: request failed %{public}s %{public}s', String(err.code), err.message);
    }
    const enabled = notificationManager.isNotificationEnabledSync();
    hilog.info(DOMAIN, TAG, 'notifications: enabled=%{public}s', String(enabled));
    return enabled;
  }

  incomingCall(caller: string): void {
    this.riskLevelShown = 'none';
    const t = this.texts();
    this.publish(ID_INCOMING, t.incomingTitle, t.incomingText + caller);
  }

  risk(level: string): void {
    if (level !== 'warn' && level !== 'high') {
      return;
    }
    if (level === this.riskLevelShown || (level === 'warn' && this.riskLevelShown === 'high')) {
      return;
    }
    this.riskLevelShown = level;
    const t = this.texts();
    if (level === 'high') {
      this.publish(ID_RISK, t.highTitle, t.highText);
    } else {
      this.publish(ID_RISK, t.warnTitle, t.warnText);
    }
  }

  callEnded(reason: string): void {
    this.cancel(ID_INCOMING);
    this.cancel(ID_RISK);
    if (reason === 'scam_blocked') {
      const t = this.texts();
      this.publish(ID_RESULT, t.blockedTitle, t.blockedText);
    }
  }

  private texts(): Texts {
    return this.lang === 'en' ? EN : PL;
  }

  private async getOpenAppAgent(): Promise<WantAgent | null> {
    if (this.openApp !== null) {
      return this.openApp;
    }
    try {
      const want: Want = { bundleName: this.context.abilityInfo.bundleName, abilityName: 'EntryAbility' };
      const info: wantAgent.WantAgentInfo = {
        wants: [want],
        actionType: wantAgent.OperationType.START_ABILITY,
        requestCode: 0,
        actionFlags: [wantAgent.WantAgentFlags.UPDATE_PRESENT_FLAG]
      };
      this.openApp = await wantAgent.getWantAgent(info);
    } catch (e) {
      const err = e as BusinessError;
      hilog.warn(DOMAIN, TAG, 'notifications: wantAgent failed %{public}s', err.message);
    }
    return this.openApp;
  }

  private async publish(id: number, title: string, text: string): Promise<void> {
    try {
      const request: notificationManager.NotificationRequest = {
        id: id,
        notificationSlotType: notificationManager.SlotType.SOCIAL_COMMUNICATION,
        content: {
          notificationContentType: notificationManager.ContentType.NOTIFICATION_CONTENT_BASIC_TEXT,
          normal: { title: title, text: text }
        },
        tapDismissed: true
      };
      const agent = await this.getOpenAppAgent();
      if (agent !== null) {
        request.wantAgent = agent;
      }
      await notificationManager.publish(request);
      hilog.info(DOMAIN, TAG, 'notifications: published id=%{public}d', id);
    } catch (e) {
      const err = e as BusinessError;
      hilog.warn(DOMAIN, TAG, 'notifications: publish id=%{public}d failed %{public}s %{public}s', id,
        String(err.code), err.message);
    }
  }

  private cancel(id: number): void {
    notificationManager.cancel(id).catch(() => {
    });
  }
}
