import { useState, useEffect, useCallback } from "react";
import type { Player, UserPreferences, EventPreferences } from "@/types/api";
import { getPlayers, getPreferences, updatePlayers, updateEvents } from "@/lib/api";

interface UsePreferencesResult {
  players: Player[];
  preferences: UserPreferences | null;
  isLoading: boolean;
  error: string | null;
  togglePlayer: (playerId: number) => Promise<void>;
  toggleEvent: (key: keyof EventPreferences, value: boolean) => Promise<void>;
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
        const updated = await updatePlayers(token, next);
        setPreferences(updated);
      } catch (e) {
        setError(e instanceof Error ? e.message : "設定の更新に失敗しました");
      }
    },
    [token, preferences]
  );

  const toggleEvent = useCallback(
    async (key: keyof EventPreferences, value: boolean) => {
      if (!token || !preferences) return;
      const next: EventPreferences = { ...preferences.event_prefs, [key]: value };
      try {
        const updated = await updateEvents(token, next);
        setPreferences(updated);
      } catch (e) {
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
    toggleEvent,
    refresh: load,
  };
}
