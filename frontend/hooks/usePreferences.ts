import { useState, useEffect, useCallback } from "react";
import type { Player, PlayerEventPrefs, UserPreferences } from "@/types/api";
import {
  getPlayers,
  getPreferences,
  updateAllPlayerPreferences,
  updatePlayers,
  updatePlayerEvents,
} from "@/lib/api";

interface UsePreferencesResult {
  players: Player[];
  preferences: UserPreferences | null;
  isLoading: boolean;
  error: string | null;
  togglePlayer: (playerId: number) => Promise<void>;
  setAllPlayersSubscribed: (enabled: boolean) => Promise<void>;
  togglePlayerEvent: (playerId: number, eventType: "home_run" | "strikeout", value: boolean) => Promise<void>;
  refresh: () => Promise<void>;
}

function buildBulkEventPrefs(players: Player[], enabled: boolean): Record<string, PlayerEventPrefs> {
  return Object.fromEntries(
    players.map((player) => {
      const prefs: PlayerEventPrefs = {};
      if (player.position === "batter" || player.position === "two_way") {
        prefs.home_run = enabled;
      }
      if (player.position === "pitcher" || player.position === "two_way") {
        prefs.strikeout = enabled;
      }
      return [String(player.id), prefs];
    })
  );
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

  const setAllPlayersSubscribed = useCallback(
    async (enabled: boolean) => {
      if (!token || !preferences) return;
      const next = enabled ? players.map((player) => player.id) : [];
      const previous = preferences;
      setPreferences({
        ...preferences,
        player_ids: next,
        event_prefs: {
          ...preferences.event_prefs,
          home_run: enabled,
          strikeout: enabled,
        },
        player_event_prefs: buildBulkEventPrefs(players, enabled),
      });
      try {
        await updateAllPlayerPreferences(token, enabled);
      } catch (e) {
        setPreferences(previous);
        setError(e instanceof Error ? e.message : "設定の更新に失敗しました");
      }
    },
    [token, preferences, players]
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
    setAllPlayersSubscribed,
    togglePlayerEvent,
    refresh: load,
  };
}
