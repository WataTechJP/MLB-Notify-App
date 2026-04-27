const appJson = require("./app.json");

const baseConfig = appJson.expo;

function validateProductionBuildEnv() {
  if (process.env.EAS_BUILD_PROFILE !== "production") {
    return;
  }

  const apiBaseUrl = process.env.EXPO_PUBLIC_API_BASE_URL?.trim();
  if (!apiBaseUrl) {
    throw new Error(
      "Production build requires EXPO_PUBLIC_API_BASE_URL to be set."
    );
  }
  if (!apiBaseUrl.startsWith("https://")) {
    throw new Error(
      "Production build requires EXPO_PUBLIC_API_BASE_URL to start with https://."
    );
  }
}

export default ({ config }: { config: typeof baseConfig }) => {
  validateProductionBuildEnv();
  return {
    ...config,
    ...baseConfig,
    extra: {
      ...config.extra,
      ...baseConfig.extra,
    },
  };
};
