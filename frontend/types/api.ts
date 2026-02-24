export interface Player {
  id: number;
  name_ja: string;
  name_en: string;
  position: "batter" | "pitcher" | "two_way";
  team: string;
}

export interface PlayerEventPrefs {
  home_run?: boolean;  // 打者 / two_way のみ
  strikeout?: boolean; // 投手 / two_way のみ
}

export interface UserPreferences {
  expo_push_token: string;
  is_active: boolean;
  player_ids: number[];
  event_prefs: Record<string, boolean>; // 後方互換として残す
  player_event_prefs: Record<string, PlayerEventPrefs>;
}

export interface RegisterUserResponse {
  id: number;
  expo_push_token: string;
  is_active: boolean;
}
