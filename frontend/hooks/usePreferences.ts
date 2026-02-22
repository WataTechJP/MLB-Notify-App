import { useState, useEffect, useCallback } from "react";
import type { Player, PlayerEventPrefs, UserPreferences } from "@/types/api";
import { getPlayers, getPreferences, updatePlayers, updatePlayerEvents } from "@/lib/api";

interface UsePreferencesResult {
  players: Player[];
  preferences: UserPreferences | null;
  isLoading: boolean;
  error: string | null;
  togglePlayer: (playerId: number) => Promise<void>;
  togglePlayerEvent: (playerId: number, eventType: "home_run" | "strikeout", value: boolean) => Promise<void>;
  refresh: () => Promise<void>;
}

export function usePreferences(token: string | null): UsePreferencesResult {
  const [players, setPlayers] = useState<Player[]>([]);
  const [preferences, setPreferences] = useState<UserPreferences | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!token) return;
    setIsLoading(true);
    setError(null);
    try {
      const [p, prefs] = await Promise.all([
        getPlayers(),
        getPreferences(token),
      ]);
      setPlayers(p);
      setPreferences(prefs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "データの取得に失敗しました");
    } finally {
      setIsLoading(false);
    }
  }, [token]);

  useEffect(() => {
    load();
  }, [load]);

  const togglePlayer = useCallback(
    async (playerId: number) => {
      if (!token || !preferences) return;
      const current = preferences.player_ids;
      const next = current.includes(playerId)
        ? current.filter((id) => id !== playerId)
        : [...current, playerId];
      try {
        await updatePlayers(token, next);
        setPreferences({ ...preferences, player_ids: next });
      } catch (e) {
        setError(e instanceof Error ? e.message : "設定の更新に失敗しました");
      }
    },
    [token, preferences]
  );

  const togglePlayerEvent = useCallback(
    async (playerId: number, eventType: "home_run" | "strikeout", value: boolean) => {
      if (!token || !preferences) return;
      const key = String(playerId);
      const current = preferences.player_event_prefs[key] ?? {};
      const optimisticPrefs = {
        ...preferences,
        player_event_prefs: {
          ...preferences.player_event_prefs,
          [key]: { ...current, [eventType]: value },
        },
      };
      // オプティミスティック更新: API完了を待たずに即座に反映
      setPreferences(optimisticPrefs);
      try {
        await updatePlayerEvents(token, playerId, { [eventType]: value });
      } catch (e) {
        // 失敗時はロールバック
        setPreferences(preferences);
        setError(e instanceof Error ? e.message : "設定の更新に失敗しました");
      }
    },
    [token, preferences]
  );

  return {
    players,
    preferences,
    isLoading,
    error,
    togglePlayer,
    togglePlayerEvent,
    refresh: load,
  };
}
