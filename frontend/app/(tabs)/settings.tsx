import { useState, useCallback } from "react";
import {
  View,
  Text,
  ScrollView,
  StyleSheet,
  ActivityIndicator,
  RefreshControl,
  TouchableOpacity,
} from "react-native";
import { usePushToken } from "@/hooks/usePushToken";
import { usePreferences } from "@/hooks/usePreferences";
import { PlayerCard } from "@/components/PlayerCard";
import { Colors } from "@/constants/colors";
import { sendDemoNotification, sendTestNotification } from "@/lib/api";
import type { Player } from "@/types/api";

const SHOW_TEST_TOOLS =
  __DEV__ || process.env.EXPO_PUBLIC_ENABLE_TEST_TOOLS === "true";

const TEAM_TO_DIVISION: Record<string, string> = {
  BAL: "アメリカンリーグ東地区",
  BOS: "アメリカンリーグ東地区",
  NYY: "アメリカンリーグ東地区",
  TB: "アメリカンリーグ東地区",
  TOR: "アメリカンリーグ東地区",
  CWS: "アメリカンリーグ中地区",
  CLE: "アメリカンリーグ中地区",
  DET: "アメリカンリーグ中地区",
  KC: "アメリカンリーグ中地区",
  MIN: "アメリカンリーグ中地区",
  HOU: "アメリカンリーグ西地区",
  LAA: "アメリカンリーグ西地区",
  OAK: "アメリカンリーグ西地区",
  SEA: "アメリカンリーグ西地区",
  TEX: "アメリカンリーグ西地区",
  ATL: "ナショナルリーグ東地区",
  MIA: "ナショナルリーグ東地区",
  NYM: "ナショナルリーグ東地区",
  PHI: "ナショナルリーグ東地区",
  WSH: "ナショナルリーグ東地区",
  CHC: "ナショナルリーグ中地区",
  CIN: "ナショナルリーグ中地区",
  MIL: "ナショナルリーグ中地区",
  PIT: "ナショナルリーグ中地区",
  STL: "ナショナルリーグ中地区",
  ARI: "ナショナルリーグ西地区",
  COL: "ナショナルリーグ西地区",
  LAD: "ナショナルリーグ西地区",
  SD: "ナショナルリーグ西地区",
  SF: "ナショナルリーグ西地区",
};

const DIVISION_ORDER = [
  "アメリカンリーグ東地区",
  "アメリカンリーグ中地区",
  "アメリカンリーグ西地区",
  "ナショナルリーグ東地区",
  "ナショナルリーグ中地区",
  "ナショナルリーグ西地区",
] as const;

const POSITION_ORDER: Record<Player["position"], number> = {
  pitcher: 0,
  two_way: 1,
  batter: 2,
};

function buildDivisionGroups(players: Player[]) {
  const grouped = new Map<string, Player[]>(
    DIVISION_ORDER.map((division) => [division, []])
  );

  for (const player of players) {
    const division = TEAM_TO_DIVISION[player.team];
    if (!division) continue;
    grouped.get(division)?.push(player);
  }

  for (const division of DIVISION_ORDER) {
    grouped.get(division)?.sort((a, b) => {
      if (a.team !== b.team) {
        return a.team.localeCompare(b.team, "en");
      }
      if (POSITION_ORDER[a.position] !== POSITION_ORDER[b.position]) {
        return POSITION_ORDER[a.position] - POSITION_ORDER[b.position];
      }
      return a.name_ja.localeCompare(b.name_ja, "ja");
    });
  }

  return DIVISION_ORDER
    .map((division) => ({
      division,
      players: grouped.get(division) ?? [],
    }))
    .filter((group) => group.players.length > 0);
}

export default function SettingsScreen() {
  const { token } = usePushToken();
  const { players, preferences, isLoading, error, togglePlayer, refresh } =
    usePreferences(token);
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ ok: boolean; msg: string } | null>(null);

  const handleRefresh = useCallback(async () => {
    setTestResult(null);
    await refresh();
  }, [refresh]);

  const handleSendTest = async () => {
    if (!token) return;
    setIsTesting(true);
    setTestResult(null);
    try {
      await sendTestNotification(token);
      setTestResult({ ok: true, msg: "送信しました！数秒後に通知が届きます" });
    } catch (e) {
      setTestResult({ ok: false, msg: e instanceof Error ? e.message : "送信に失敗しました" });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSendDemo = async (demoType: "batter" | "pitcher" | "mlb_first") => {
    if (!token) return;
    setIsTesting(true);
    setTestResult(null);
    try {
      await sendDemoNotification(token, demoType);
      setTestResult({ ok: true, msg: "デモ通知を送信しました（数秒後に届きます）" });
    } catch (e) {
      setTestResult({ ok: false, msg: e instanceof Error ? e.message : "送信に失敗しました" });
    } finally {
      setIsTesting(false);
    }
  };

  if (isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.accent} />
      </View>
    );
  }

  const divisionGroups = buildDivisionGroups(players);

  return (
    <ScrollView
      style={styles.container}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl
          refreshing={isLoading}
          onRefresh={handleRefresh}
          tintColor={Colors.accent}
        />
      }
    >
      <Text style={styles.heading}>設定</Text>

      {error && (
        <View style={styles.errorBox}>
          <Text style={styles.errorText}>{error}</Text>
        </View>
      )}

      {/* 選手設定 */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>
          フォローする選手 ({preferences?.player_ids.length ?? 0}/{players.length})
        </Text>
        {divisionGroups.map((group) => (
          <View key={group.division} style={styles.divisionBlock}>
            <Text style={styles.divisionTitle}>{group.division}</Text>
            {group.players.map((player) => (
              <PlayerCard
                key={player.id}
                player={player}
                isSubscribed={preferences?.player_ids.includes(player.id) ?? false}
                eventPrefs={preferences?.player_event_prefs[String(player.id)]}
                onToggle={() => togglePlayer(player.id)}
                showToggle={true}
              />
            ))}
          </View>
        ))}
      </View>

      {SHOW_TEST_TOOLS && (
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>通知テスト</Text>
          <View style={styles.demoGrid}>
            <TouchableOpacity
              style={[styles.demoButton, isTesting && styles.testButtonDisabled]}
              onPress={() => handleSendDemo("batter")}
              disabled={isTesting || !token}
              activeOpacity={0.7}
            >
              <Text style={styles.demoButtonText}>打者デモ</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.demoButton, isTesting && styles.testButtonDisabled]}
              onPress={() => handleSendDemo("pitcher")}
              disabled={isTesting || !token}
              activeOpacity={0.7}
            >
              <Text style={styles.demoButtonText}>投手デモ</Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.demoButton, isTesting && styles.testButtonDisabled]}
              onPress={() => handleSendDemo("mlb_first")}
              disabled={isTesting || !token}
              activeOpacity={0.7}
            >
              <Text style={styles.demoButtonText}>MLB初デモ</Text>
            </TouchableOpacity>
          </View>
          <TouchableOpacity
            style={[styles.testButton, isTesting && styles.testButtonDisabled]}
            onPress={handleSendTest}
            disabled={isTesting || !token}
            activeOpacity={0.7}
          >
            {isTesting ? (
              <ActivityIndicator size="small" color={Colors.text} />
            ) : (
              <Text style={styles.testButtonText}>テスト通知を送る</Text>
            )}
          </TouchableOpacity>
          {testResult && (
            <Text style={[styles.testResultText, testResult.ok ? styles.testResultOk : styles.testResultError]}>
              {testResult.msg}
            </Text>
          )}
        </View>
      )}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
  },
  content: {
    padding: 20,
    paddingTop: 16,
  },
  centered: {
    flex: 1,
    backgroundColor: Colors.background,
    alignItems: "center",
    justifyContent: "center",
  },
  heading: {
    fontSize: 26,
    fontWeight: "800",
    color: Colors.text,
    marginBottom: 24,
  },
  section: {
    marginBottom: 28,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: "600",
    color: Colors.subtext,
    textTransform: "uppercase",
    letterSpacing: 1,
    marginBottom: 12,
  },
  divisionBlock: {
    marginBottom: 14,
  },
  divisionTitle: {
    fontSize: 13,
    fontWeight: "700",
    color: Colors.text,
    marginTop: 6,
    marginBottom: 4,
  },
  errorBox: {
    backgroundColor: "#2a1a1a",
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
    borderWidth: 1,
    borderColor: Colors.accent,
  },
  errorText: {
    color: Colors.accent,
    fontSize: 13,
  },
  testButton: {
    backgroundColor: Colors.card,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: "center",
    borderWidth: 1,
    borderColor: Colors.border,
  },
  demoGrid: {
    flexDirection: "row",
    gap: 8,
    marginBottom: 8,
  },
  demoButton: {
    flex: 1,
    backgroundColor: Colors.card,
    borderRadius: 12,
    paddingVertical: 12,
    alignItems: "center",
    borderWidth: 1,
    borderColor: Colors.border,
  },
  demoButtonText: {
    color: Colors.text,
    fontSize: 13,
    fontWeight: "600",
  },
  testButtonDisabled: {
    opacity: 0.5,
  },
  testButtonText: {
    color: Colors.text,
    fontSize: 15,
    fontWeight: "600",
  },
  testResultText: {
    marginTop: 10,
    fontSize: 13,
    textAlign: "center",
  },
  testResultOk: {
    color: Colors.success,
  },
  testResultError: {
    color: Colors.accent,
  },
});
