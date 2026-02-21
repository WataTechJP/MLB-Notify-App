import { useState, useEffect } from "react";
import { getPushToken } from "@/lib/storage";

export function usePushToken() {
  const [token, setToken] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    getPushToken()
      .then(setToken)
      .finally(() => setIsLoading(false));
  }, []);

  return { token, isLoading, setToken };
}
