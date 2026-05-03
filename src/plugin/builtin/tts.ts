import { pluginRegistry } from "../registry";
import { TTSPlugin } from "../types";

export function registerTTSPlugins(): void {
  pluginRegistry.register({
    name: "test",
    displayName: "Test TTS (Not Configured)",
    version: "1.0.0",
    type: "tts",
    description: "Placeholder — set TTS_SERVER in .env",
    activate: () => ({
      ttsProcessor: async (_text: string) => ({ duration: 0 }),
    }),
  } as TTSPlugin);

  pluginRegistry.register({
    name: "piper",
    displayName: "Piper TTS",
    version: "1.0.0",
    type: "tts",
    audioFormat: "wav",
    description: "Piper local text-to-speech",
    activate: () => {
      const ttsProcessor = require("../../cloud-api/local/piper-tts").default;
      return { ttsProcessor };
    },
  } as TTSPlugin);
}
