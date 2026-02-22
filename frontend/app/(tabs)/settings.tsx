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
import { sendTestNotification } from "@/lib/api";

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

  if (isLoading) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Colors.accent} />
      </View>
    );
  }

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
        {players.map((player) => (
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

      {/* 通知テスト */}
      <View style={styles.section}>
        <Text style={styles.sectionTitle}>通知テスト</Text>
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
