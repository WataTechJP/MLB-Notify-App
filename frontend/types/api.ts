export interface Player {
  id: number;
  name_ja: string;
  name_en: string;
  position: "batter" | "pitcher" | "two_way";
  team: string;
}

export interface EventPreferences {
  home_run: boolean;
  strikeout: boolean;
}

export interface UserPreferences {
  expo_push_token: string;
  is_active: boolean;
  player_ids: number[];
  event_prefs: EventPreferences;
}

export interface RegisterUserResponse {
  id: number;
  expo_push_token: string;
  is_active: boolean;
}
