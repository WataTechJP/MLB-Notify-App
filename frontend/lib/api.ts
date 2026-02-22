import type {
  Player,
  PlayerEventPrefs,
  UserPreferences,
  RegisterUserResponse,
} from "@/types/api";

const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

if (!__DEV__ && !API_BASE.startsWith("https://")) {
  console.error("[API] 本番環境ではHTTPSを使用してください。EXPO_PUBLIC_API_BASE_URLをhttps://で始まるURLに設定してください。");
}

function encodedToken(token: string): string {
  return encodeURIComponent(token);
}

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`;
  let res: Response;
  try {
    res = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...(options?.headers ?? {}),
      },
    });
  } catch {
    throw new Error("サーバーに接続できませんでした。ネットワーク接続を確認してください。");
  }
  if (!res.ok) {
    if (__DEV__) {
      const body = await res.text();
      console.error(`[API] ${res.status} ${url}:`, body);
    }
    throw new Error(`通信エラーが発生しました (${res.status})`);
  }
  if (res.status === 204) {
    return undefined as T;
  }
  return res.json() as Promise<T>;
}

export async function registerUser(
  token: string
): Promise<RegisterUserResponse> {
  return request<RegisterUserResponse>("/api/v1/users/register", {
    method: "POST",
    body: JSON.stringify({ expo_push_token: token }),
  });
}

export async function getPlayers(): Promise<Player[]> {
  return request<Player[]>("/api/v1/players");
}

export async function getPreferences(token: string): Promise<UserPreferences> {
  return request<UserPreferences>(
    `/api/v1/preferences/${encodedToken(token)}`
  );
}

export async function updatePlayers(
  token: string,
  playerIds: number[]
): Promise<void> {
  return request<void>(
    `/api/v1/preferences/${encodedToken(token)}/players`,
    {
      method: "PUT",
      body: JSON.stringify({ player_ids: playerIds }),
    }
  );
}

export async function updatePlayerEvents(
  token: string,
  playerId: number,
  prefs: PlayerEventPrefs
): Promise<void> {
  return request<void>(
    `/api/v1/preferences/${encodedToken(token)}/player-events`,
    {
      method: "PUT",
      body: JSON.stringify({ player_id: playerId, ...prefs }),
    }
  );
}
