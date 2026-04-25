import type {
  Player,
  PlayerEventPrefs,
  UserPreferences,
  RegisterUserResponse,
} from "@/types/api";

const API_BASE =
  process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8001";
const RETRYABLE_STATUSES = new Set([502, 503, 504]);
const RETRY_DELAYS_MS = [1000, 3000];

if (!__DEV__ && !API_BASE.startsWith("https://")) {
  console.error("[API] 本番環境ではHTTPSを使用してください。EXPO_PUBLIC_API_BASE_URLをhttps://で始まるURLに設定してください。");
}

function encodedToken(token: string): string {
  return encodeURIComponent(token);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function isRetryableRequest(path: string, method: string): boolean {
  if (method === "GET" || method === "PUT") {
    return true;
  }
  return method === "POST" && path === "/api/v1/users/register";
}

async function request<T>(
  path: string,
  options?: RequestInit
): Promise<T> {
  const url = `${API_BASE}${path}`;
  const method = (options?.method ?? "GET").toUpperCase();
  const retryable = isRetryableRequest(path, method);
  const maxAttempts = retryable ? 3 : 1;

  for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
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
      if (attempt < maxAttempts) {
        await sleep(RETRY_DELAYS_MS[attempt - 1] ?? 2000);
        continue;
      }
      throw new Error("サーバーに接続できませんでした。ネットワーク接続を確認してください。");
    }

    if (res.ok) {
      if (res.status === 204) {
        return undefined as T;
      }
      return res.json() as Promise<T>;
    }

    if (retryable && RETRYABLE_STATUSES.has(res.status) && attempt < maxAttempts) {
      if (__DEV__) {
        console.warn(`[API] retry ${attempt}/${maxAttempts - 1} ${method} ${url} status=${res.status}`);
      }
      await sleep(RETRY_DELAYS_MS[attempt - 1] ?? 2000);
      continue;
    }

    // 本番でも最低限ステータスコードとURLはログする
    console.error(`[API] ${res.status} ${url}`);
    if (__DEV__) {
      const body = await res.text();
      console.error(`[API] response body:`, body);
    }
    throw new Error(`通信エラーが発生しました (${res.status})`);
  }

  throw new Error("通信エラーが発生しました");
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

export async function sendTestNotification(token: string): Promise<void> {
  return request<void>("/api/v1/test/send-notification", {
    method: "POST",
    body: JSON.stringify({ push_token: token }),
  });
}

export async function sendDemoNotification(
  token: string,
  demoType: "batter" | "pitcher" | "mlb_first"
): Promise<void> {
  return request<void>("/api/v1/test/send-demo-notification", {
    method: "POST",
    body: JSON.stringify({ push_token: token, demo_type: demoType }),
  });
}
