import * as SecureStore from "expo-secure-store";

const PUSH_TOKEN_KEY = "mlb_push_token";

export async function savePushToken(token: string): Promise<void> {
  await SecureStore.setItemAsync(PUSH_TOKEN_KEY, token);
}

export async function getPushToken(): Promise<string | null> {
  return await SecureStore.getItemAsync(PUSH_TOKEN_KEY);
}

export async function clearPushToken(): Promise<void> {
  await SecureStore.deleteItemAsync(PUSH_TOKEN_KEY);
}
