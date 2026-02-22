import { useEffect } from "react";
import { Stack, router } from "expo-router";
import { StatusBar } from "expo-status-bar";
import { getPushToken } from "@/lib/storage";
import { setupNotificationHandlers } from "@/lib/notifications";
import { registerUser } from "@/lib/api";
import { Colors } from "@/constants/colors";

export default function RootLayout() {
  useEffect(() => {
    const cleanup = setupNotificationHandlers();
    return cleanup;
  }, []);

  useEffect(() => {
    getPushToken().then(async (token) => {
      if (token) {
        // 既存ユーザーも /register を呼ぶことで player_event_prefs のシードを保証する
        // （/register は冪等: 既存ユーザーは is_active を更新し、未登録の選手別イベント設定を補完する）
        try {
          await registerUser(token);
        } catch {
          // 登録失敗時もアプリは起動する（オフライン時など）
        }
        router.replace("/(tabs)");
      } else {
        router.replace("/onboarding");
      }
    });
  }, []);

  return (
    <>
      <StatusBar style="light" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: Colors.background },
          headerTintColor: Colors.text,
          contentStyle: { backgroundColor: Colors.background },
          headerShown: false,
        }}
      >
        <Stack.Screen name="onboarding" options={{ headerShown: false }} />
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
      </Stack>
    </>
  );
}
