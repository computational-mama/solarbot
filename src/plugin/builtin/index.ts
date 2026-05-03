import { registerASRPlugins } from "./asr";
import { registerLLMPlugins } from "./llm";
import { registerTTSPlugins } from "./tts";
import { registerLLMToolsPlugins } from "./llm-tools";

export function registerBuiltinPlugins(): void {
  registerASRPlugins();
  registerLLMPlugins();
  registerTTSPlugins();
  registerLLMToolsPlugins();
}
