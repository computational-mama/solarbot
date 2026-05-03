import { pluginRegistry } from "../registry";
import { ASRPlugin } from "../types";

export function registerASRPlugins(): void {
  pluginRegistry.register({
    name: "test",
    displayName: "Test ASR (Not Configured)",
    version: "1.0.0",
    type: "asr",
    description: "Placeholder — set ASR_SERVER in .env",
    activate: () => ({
      recognizeAudio: async (_audioPath: string) => "ASR not configured",
    }),
  } as ASRPlugin);

  pluginRegistry.register({
    name: "faster-whisper",
    displayName: "Faster Whisper ASR",
    version: "1.0.0",
    type: "asr",
    audioFormat: "wav",
    description: "Faster Whisper optimized speech recognition",
    activate: () => {
      const { recognizeAudio } = require("../../cloud-api/local/faster-whisper-asr");
      return { recognizeAudio };
    },
  } as ASRPlugin);
}
