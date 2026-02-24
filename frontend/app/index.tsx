import { useEffect } from "react";
import { View, ActivityIndicator, StyleSheet } from "react-native";
import { router } from "expo-router";
import { getPushToken } from "@/lib/storage";
import { Colors } from "@/constants/colors";

export default function Index() {
  useEffect(() => {
    getPushToken().then((token) => {
      if (token) {
        router.replace("/(tabs)");
      } else {
        router.replace("/onboarding");
      }
    });
  }, []);

  return (
    <View style={styles.container}>
      <ActivityIndicator size="large" color={Colors.accent} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: Colors.background,
    alignItems: "center",
    justifyContent: "center",
  },
});
