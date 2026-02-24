import * as Notifications from "expo-notifications";
import Constants from "expo-constants";
import { Platform } from "react-native";

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: false,
    shouldShowBanner: true,
    shouldShowList: true,
  }),
});

export async function requestAndGetToken(): Promise<string> {
  if (Platform.OS === "android") {
    await Notifications.setNotificationChannelAsync("default", {
      name: "default",
      importance: Notifications.AndroidImportance.MAX,
      vibrationPattern: [0, 250, 250, 250],
    });
  }

  const { status: existingStatus } = await Notifications.getPermissionsAsync();
  let finalStatus = existingStatus;

  if (existingStatus !== "granted") {
    const { status } = await Notifications.requestPermissionsAsync();
    finalStatus = status;
  }

  if (finalStatus !== "granted") {
    throw new Error("通知の許可が得られませんでした。設定から通知を有効にしてください。");
  }

  const projectIdFromExtra = Constants.expoConfig?.extra?.eas?.projectId;
  const projectIdFromEas = Constants.easConfig?.projectId;
  const projectIdFromEnv = process.env.EXPO_PUBLIC_EAS_PROJECT_ID;
  const projectId =
    [projectIdFromExtra, projectIdFromEas, projectIdFromEnv]
      .find((id): id is string => typeof id === "string" && id.trim().length > 0)
      ?.trim() ?? null;

  if (!projectId) {
    throw new Error(
      [
        "No projectID found.",
        "EAS project ID を設定してください。",
        "1) Expo Dashboard > Project > Project ID を確認",
        "2) frontend/.env に EXPO_PUBLIC_EAS_PROJECT_ID=<Project ID> を追加",
        "3) 開発サーバーを再起動",
      ].join("\n")
    );
  }

  const tokenData = await Notifications.getExpoPushTokenAsync({ projectId });

  return tokenData.data;
}

export function setupNotificationHandlers(
  onNotification?: (notification: Notifications.Notification) => void,
  onResponse?: (response: Notifications.NotificationResponse) => void
): () => void {
  const notifSub = Notifications.addNotificationReceivedListener((notif) => {
    onNotification?.(notif);
  });

  const responseSub = Notifications.addNotificationResponseReceivedListener(
    (response) => {
      onResponse?.(response);
    }
  );

  return () => {
    notifSub.remove();
    responseSub.remove();
  };
}
