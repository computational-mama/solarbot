# agents.md — Solarbot AI Agent Guide

This file is for AI coding agents (Claude Code, Cursor, Copilot, etc.) working in this repository. It supplements `CLAUDE.md` with practical rules for making changes safely.

---

## Must-know before touching anything

- **TypeScript changes require a rebuild** (`npm run build`) before they take effect. `.env` changes take effect on restart only.
- **Two processes always run together**: Node.js (`src/`) and Python (`python/chatbot-ui.py`). They talk over a local TCP socket on port **12345**. Changes to the `Status` interface in `src/device/display.ts` must be mirrored in the Python socket handler.
- **No tests exist** (`npm test` is a no-op). Verify changes by running the bot or using dev mode (see below).
- **Dev mode (no hardware)**: set `WHISPLAY_WEB_ENABLED=true`, `WEB_AUDIO_ENABLED=true`, and `WHISPLAY_DEVICE_ENABLED=false` in `.env`, then open `http://localhost:17880`.

---

## Architecture map

```
src/index.ts
  └── ChatFlow (src/core/ChatFlow.ts)
        ├── FlowStateMachine  (src/core/chat-flow/stateMachine.ts)
        │     └── flowStates  (src/core/chat-flow/states.ts)
        ├── StreamResponser   (src/core/StreamResponser.ts)
        ├── display()         (src/device/display.ts)  ──TCP:12345──► python/chatbot-ui.py
        └── pluginRegistry    (src/plugin/)
              ├── ASR plugin  → recognizeAudio()
              ├── LLM plugin  → chatWithLLMStream()
              ├── TTS plugin  → ttsProcessor()
              └── llm-tools   → LLM function-calling tools
```

### State machine flow

```
sleep → listening → asr → answer → sleep
                              ↘ image → sleep
        wake_listening ↗ (via wake word)
```

- `sleep`: idle. 4-minute idle timer blanks LCD (`brightness: 0`). Button press → `listening`.
- `listening`: hold-to-talk manual recording.
- `wake_listening`: auto voice-level detection triggered by wake word.
- `asr`: sends recording to faster-whisper; button press mid-ASR → `listening`.
- `answer`: streams LLM response, plays TTS, updates display. Double-click → `sleep`. Single press mid-answer → `listening`.
- `image`: fullscreens a generated image; button press → `listening`.

---

## How to add or change things

### Add an LLM function-calling tool

1. Copy `src/config/custom-tools/template.ts`, implement your tool.
2. Register it in `src/plugin/builtin/llm-tools.ts` → `registerLLMToolsPlugins()`.
3. `npm run build` — rebuild required.

Tool `func` must return a string. The return value is shown on the display and injected back into the LLM context.

Special return values:
- `generateImage` tool returning `[success]...` → transitions to `image` state and shows the image.
- `endConversation` tool returning `[success]...` → sets `endAfterAnswer = true`, returns to `sleep` after TTS finishes.

### Add an external plugin (ASR / LLM / TTS / image-gen / vision)

Drop a directory into `plugins/` (or publish an npm package named `whisplay-plugin-*`). The loader auto-discovers it. Each plugin exports a default object matching one of the typed interfaces in `src/plugin/types.ts`. The plugin's own `.env` file is scoped and never pollutes `process.env`.

### Change what shows on the display

Call `display(Partial<Status>)` (exported from `src/device/display.ts`). Every call forces `brightness: 100` unless you pass it explicitly. Key fields:

| Field | Purpose |
|---|---|
| `status` | Drives animation frame selection (e.g. `"idle"`, `"listening"`, `"answering"`) |
| `emoji` | Shown in header |
| `text` | Main body text; `{count}` replaced by live elapsed-second counter |
| `RGB` | Hex color for RGB LED |
| `image` | Path to image for fullscreen mode; `""` to exit image mode |
| `rag_icon_visible` | Show/hide the RAG icon in the header |
| `brightness` | 0–100; defaults to 100 on every call |

### Change the chat state machine

State handlers live in `src/core/chat-flow/states.ts`. Each handler is a plain function that:
- Registers button callbacks via `onButtonPressed`, `onButtonReleased`, `onButtonDoubleClick`
- Calls `display()` to update the screen
- Transitions via `ctx.transitionTo(flowName)`

`transitionTo` also calls `display({ text_input_enabled: flowName === "sleep" })` automatically.

### Add a new chat state

1. Add the state name to the `FlowName` union in `src/core/chat-flow/types.ts`.
2. Add the handler to `flowStates` in `src/core/chat-flow/states.ts`.
3. Rebuild.

### Change the Python display layer

`python/chatbot-ui.py` renders the LCD. The socket server at port 12345 accepts JSON matching the `Status` shape. If you add fields to `Status` in TypeScript, add handling for them in the Python socket receiver. Animation frames are PNG sequences in `python/animations/<state>/` (00.png, 01.png, 02.png, …).

---

## Key contracts

### `display()` call — do and don't

```typescript
// Good — partial update, brightness defaults to 100
display({ status: "listening", RGB: "#00ff00", text: "Listening..." });

// Good — explicitly blank the screen
display({ brightness: 0 });

// Mistake — brightness is always overridden to 100 unless you pass it
// You cannot dim the screen by omitting brightness in a display() call
```

### Plugin `activate()` return

Each plugin's `activate(ctx)` must return (or resolve to) the provider interface synchronously or asynchronously. The registry calls `activate` once; the result is cached. Read all config from `ctx.env` (not `process.env`) so the plugin's own `.env` is respected.

### ASR short-audio guard

`ChatFlow.recognizeAudio()` skips audio shorter than 500 ms (for manual recording). Auto-recording from wake word skips this guard. Don't bypass it for manual-listening flows.

---

## Environment variable reference

| Variable | Default | Notes |
|---|---|---|
| `ASR_SERVER` | `faster-whisper` | |
| `LLM_SERVER` | `ollama` | |
| `TTS_SERVER` | `piper` | |
| `IMAGE_GENERATION_SERVER` | _(empty)_ | Optional |
| `VISION_SERVER` | _(empty)_ | Optional |
| `OLLAMA_ENDPOINT` | `http://localhost:11434` | |
| `OLLAMA_MODEL` | `qwen2.5:0.5b` | |
| `SERVE_OLLAMA` | `true` | Auto-start Ollama |
| `FASTER_WHISPER_HOST` | `localhost` | |
| `FASTER_WHISPER_PORT` | `8803` | |
| `FASTER_WHISPER_MODEL_SIZE_OR_PATH` | `tiny` | |
| `FASTER_WHISPER_LANGUAGE` | `en` | |
| `SERVE_FASTER_WHISPER` | `false` | Auto-start Whisper server |
| `PIPER_BINARY_PATH` | _(required)_ | |
| `PIPER_MODEL_PATH` | _(required)_ | `.onnx` file |
| `ENABLE_RAG` | `true` | |
| `EMBEDDING_SERVER` | `ollama` | |
| `OLLAMA_EMBEDDING_MODEL` | `nomic-embed-text` | |
| `VECTOR_DB_SERVER` | `qdrant` | |
| `QDRANT_HOST` | `http://localhost:6333` | |
| `RAG_KNOWLEDGE_SCORE_THRESHOLD` | `0.8` | 0.0–1.0 |
| `ENABLE_KNOWLEDGE_SUMMARY` | `ollama` | Summarize chunks before indexing |
| `SYSTEM_PROMPT` | _(see .env.template)_ | LLM personality |
| `DEFAULT_EMOJI` | `🌞` | Header emoji when none extracted from LLM text |
| `UI_BACKGROUND_COLOR` | `#FFF5D1` | LCD background |
| `CHAT_HISTORY_RESET_TIME` | `300` | Seconds of inactivity before history clears |
| `WAKE_WORD_ENABLED` | `false` | |
| `WAKE_WORDS` | `hey_jarvis` | Comma-separated |
| `WAKE_WORD_THRESHOLD` | `0.5` | |
| `WAKE_WORD_IDLE_TIMEOUT_SEC` | `60` | Seconds before wake session ends |
| `WAKE_WORD_RECORD_MAX_SEC` | `60` | Max recording length in wake mode |
| `WAKE_WORD_END_KEYWORDS` | `byebye,goodbye,stop` | Words that end a wake session |
| `WHISPLAY_DEVICE_ENABLED` | `true` | Set `false` to run without hardware |
| `WHISPLAY_WEB_ENABLED` | `false` | Enable browser-based dev UI |
| `WHISPLAY_WEB_PORT` | `17880` | |
| `WHISPLAY_WEB_HOST` | `0.0.0.0` | |
| `WEB_AUDIO_ENABLED` | `false` | Browser mic/speaker |
| `WEB_CAMERA_ENABLED` | `false` | Browser camera |
| `ENABLE_CAMERA` | `false` | Physical camera |
| `WHISPLAY_ADMIN_PORT` | _(empty)_ | Enable admin UI |
| `ADMIN_TOKEN` | _(empty)_ | Bearer token for admin UI |
| `WHISPLAY_CAMERA_DAEMON_PORT` | `18765` | Camera daemon socket port |
| `HTTPS_PROXY` | _(empty)_ | Outbound proxy |

---

## File map

```
src/
  index.ts                    — entry: starts admin server, status pollers, ChatFlow
  core/
    ChatFlow.ts               — main orchestrator, wake word session management
    StreamResponser.ts        — sentence-by-sentence TTS queue
    chat-flow/
      states.ts               — all state handler functions
      stateMachine.ts         — transition logic
      types.ts                — FlowName, FlowStateHandler, ChatFlowContext
  device/
    display.ts                — WhisplayDisplay class, Status interface, singleton exports
    audio.ts                  — recordAudioManually, recordAudio, getDynamicVoiceDetectLevel
    battery.ts                — battery level polling
    voice-detect.ts           — voice activity detection
    wakeword.ts               — WakeWordListener (wraps openwakeword)
    web-audio-bridge.ts       — browser mic/speaker/camera bridge
    web-display.ts            — WebSocket server for browser UI
  cloud-api/
    server.ts                 — activates plugins, exports recognizeAudio / chatWithLLMStream / ttsProcessor
    llm.ts                    — LLM streaming, chat history, thinking token handling
    knowledge.ts              — RAG query via Qdrant
    local/
      faster-whisper-asr.ts
      ollama-llm.ts
      ollama-embedding.ts
      ollama-vision.ts
      piper-tts.ts
      qdrant-vectordb.ts
  config/
    llm-config.ts             — LLM model / params
    custom-tools/
      template.ts             — copy this to build a new LLM tool
  plugin/
    index.ts                  — re-exports registry + provider types
    registry.ts               — PluginRegistry: register, activate
    loader.ts                 — discovers plugins/ dir and whisplay-plugin-* npm packages
    builtin.ts                — registers all built-in plugins
    builtin/
      asr.ts                  — faster-whisper ASR plugin
      llm.ts                  — ollama LLM plugin
      tts.ts                  — piper TTS plugin
      llm-tools.ts            — volume control tool; register custom tools here
    types.ts                  — Plugin, PluginBase, provider interfaces, PluginContext
  admin/
    admin-server.ts           — HTTP admin API (env read/write, knowledge upload, reindex)
  status/
    battery-status.ts         — polls battery, calls display({ battery_level, battery_color })
    wifi-status.ts            — polls wifi signal
    vpn-status.ts             — polls VPN state
  type/
    index.ts                  — shared types (Message, LLMTool, TTSResult, server enums)
  utils/
    index.ts                  — splitSentences, extractEmojis, getCurrentTimeTag, …
    dir.ts                    — recordingsDir, knowledgeDir, imageDir, ttsDir
    image.ts                  — getLatestGenImg, getLatestDisplayImg
    knowledge.ts              — loadKnowledgeFiles
    volume.ts                 — setVolumeByAmixer, getCurrentLogPercent

python/
  chatbot-ui.py               — LCD render thread + socket server (port 12345)
  camera.py                   — camera daemon
  whisplay.py                 — WhisplayBoard hardware abstraction
  utils.py                    — Python helpers
  animations/                 — PNG frame sequences per state name

knowledge/                    — drop .txt / .md / .pdf here, then run npm run index-knowledge
voices/                       — Piper .onnx voice model files
web/
  admin/index.html            — admin UI frontend
docker/
  docker-compose.yml          — faster-whisper, qdrant, optional ollama/piper services
```

---

## Common pitfalls

- Forgetting `npm run build` after TypeScript edits — the `dist/` output is stale.
- Calling `display()` and expecting brightness to persist — it always resets to 100.
- Adding a `Status` field in TypeScript but not in the Python socket handler — the field is silently ignored.
- Using `process.env` inside a plugin instead of `ctx.env` — the plugin's own `.env` won't be applied.
- Indexing knowledge files but not restarting the bot — RAG queries run at bot startup.
- Modifying state in a state handler after `transitionTo()` has been called — the new state has already registered its own callbacks; your changes will be overwritten.
