import { pluginRegistry } from "../registry";
import { LLMPlugin } from "../types";

export function registerLLMPlugins(): void {
  pluginRegistry.register({
    name: "test",
    displayName: "Test LLM (Not Configured)",
    version: "1.0.0",
    type: "llm",
    description: "Placeholder — set LLM_SERVER in .env",
    activate: () => ({
      chatWithLLMStream: async (
        _inputMessages: any[],
        partialCallback: (partialAnswer: string) => void,
        endCallBack: () => void,
      ) => {
        partialCallback("LLM not configured");
        endCallBack();
      },
      resetChatHistory: () => {},
    }),
  } as LLMPlugin);

  pluginRegistry.register({
    name: "ollama",
    displayName: "Ollama LLM",
    version: "1.0.0",
    type: "llm",
    description: "Ollama local large language model",
    activate: () => {
      const mod = require("../../cloud-api/local/ollama-llm").default;
      return {
        chatWithLLMStream: mod.chatWithLLMStream,
        resetChatHistory: mod.resetChatHistory,
        summaryTextWithLLM: mod.summaryTextWithLLM,
      };
    },
  } as LLMPlugin);
}
