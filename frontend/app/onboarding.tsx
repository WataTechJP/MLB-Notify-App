import { useState } from "react";
import {
  View,
  Text,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  ScrollView,
} from "react-native";
import { router } from "expo-router";
import { requestAndGetToken } from "@/lib/notifications";
import { registerUser } from "@/lib/api";
import { savePushToken } from "@/lib/storage";
import { Colors } from "@/constants/colors";

export default function Onboarding() {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleAllow() {
    setIsLoading(true);
    setError(null);
    try {
      const token = await requestAndGetToken();
      await registerUser(token);
      await savePushToken(token);
      router.replace("/(tabs)");
    } catch (e) {
      const message =
        e instanceof Error ? e.message : "エラーが発生しました。もう一度お試しください。";
      setError(message);
      Alert.alert("エラー", message);
    } finally {
      setIsLoading(false);
    }
  }

  return (
    <ScrollView
      contentContainerStyle={styles.container}
      bounces={false}
    >
      <View style={styles.iconContainer}>
        <Text style={styles.icon}>⚾</Text>
      </View>

      <Text style={styles.title}>MLB 日本人選手{"\n"}通知アプリ</Text>

      <Text style={styles.subtitle}>
        ホームランや奪三振をリアルタイムで通知します
      </Text>

      <View style={styles.features}>
        <FeatureItem emoji="⚾" text="ホームラン速報" />
        <FeatureItem emoji="🔥" text="奪三振速報" />
        <FeatureItem emoji="🎯" text="フォロー選手をカスタマイズ" />
        <FeatureItem emoji="🔔" text="プッシュ通知でリアルタイム配信" />
      </View>

      {error && <Text style={styles.error}>{error}</Text>}

      <TouchableOpacity
        style={[styles.button, isLoading && styles.buttonDisabled]}
        onPress={handleAllow}
        disabled={isLoading}
        activeOpacity={0.8}
      >
        {isLoading ? (
          <ActivityIndicator color={Colors.text} />
        ) : (
          <Text style={styles.buttonText}>通知を許可して始める</Text>
        )}
      </TouchableOpacity>

      <Text style={styles.note}>
        通知はいつでもOFFにできます
      </Text>
    </ScrollView>
  );
}

function FeatureItem({ emoji, text }: { emoji: string; text: string }) {
  return (
    <View style={styles.featureItem}>
      <Text style={styles.featureEmoji}>{emoji}</Text>
      <Text style={styles.featureText}>{text}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    backgroundColor: Colors.background,
    alignItems: "center",
    justifyContent: "center",
    padding: 32,
    paddingTop: 80,
    paddingBottom: 60,
  },
  iconContainer: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: Colors.card,
    alignItems: "center",
    justifyContent: "center",
    marginBottom: 24,
    borderWidth: 2,
    borderColor: Colors.accent,
  },
  icon: {
    fontSize: 48,
  },
  title: {
    fontSize: 28,
    fontWeight: "800",
    color: Colors.text,
    textAlign: "center",
    lineHeight: 36,
    marginBottom: 12,
  },
  subtitle: {
    fontSize: 15,
    color: Colors.subtext,
    textAlign: "center",
    marginBottom: 36,
    lineHeight: 22,
  },
  features: {
    width: "100%",
    gap: 12,
    marginBottom: 40,
  },
  featureItem: {
    flexDirection: "row",
    alignItems: "center",
    backgroundColor: Colors.card,
    borderRadius: 12,
    padding: 16,
    gap: 12,
    borderWidth: 1,
    borderColor: Colors.border,
  },
  featureEmoji: {
    fontSize: 24,
  },
  featureText: {
    fontSize: 15,
    color: Colors.text,
    fontWeight: "500",
  },
  error: {
    color: Colors.accent,
    textAlign: "center",
    marginBottom: 16,
    fontSize: 14,
  },
  button: {
    backgroundColor: Colors.accent,
    borderRadius: 14,
    paddingVertical: 16,
    paddingHorizontal: 32,
    width: "100%",
    alignItems: "center",
    marginBottom: 16,
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: Colors.text,
    fontSize: 17,
    fontWeight: "700",
  },
  note: {
    color: Colors.subtext,
    fontSize: 12,
  },
});
