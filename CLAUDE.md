# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Build TypeScript → dist/
npm run build

# Run (after build)
bash run_chatbot.sh        # preferred — sets audio card, loads .env, starts yarn/npm
npm start                  # bare node start, skips audio setup

# Stop cleanly (blanks LCD)
bash stop_chatbot.sh

# Index knowledge base into Qdrant
npm run index-knowledge

# Install as a systemd service (auto-start on boot)
bash startup.sh

# View live logs (when running as a service)
tail -f ~/solarbot/chatbot.log
```

There are no tests (`npm test` is a no-op).

TypeScript changes always require a rebuild before they take effect. `.env` changes (system prompt, model, thresholds) take effect on restart without a rebuild.

---

## Architecture

### Process model

Two processes run together and communicate over a local TCP socket on port **12345**:

1. **Node.js** (`src/`) — chat logic, ASR/LLM/TTS pipeline, state machine. Spawns the Python process on startup.
2. **Python** (`python/chatbot-ui.py`) — owns the physical LCD, RGB LED, GPIO button, and SPI hardware via `WhisplayBoard`. Runs a render thread and a socket server.

Node sends JSON status updates to Python over the socket; Python fires button events back. The `WhisplayDisplay` class (`src/device/display.ts`) is the Node-side abstraction — call `display({ status, text, brightness, RGB, ... })` to update the screen. Every `display()` call forces `brightness: 100` unless you explicitly pass a different value.

### Chat state machine

`ChatFlow` (`src/core/ChatFlow.ts`) owns a `FlowStateMachine` that cycles through named states defined in `src/core/chat-flow/states.ts`:

```
sleep → listening → asr → answer → sleep
                              ↘ image → sleep
        wake_listening ↗ (via wake word)
```

- **sleep**: idle, screen shows prompt. 4-minute idle timer blanks the LCD (`brightness: 0`); any button press restores it and transitions to `listening`.
- **listening**: records audio manually (hold-to-talk).
- **wake_listening**: auto voice-level detection, used after wake word.
- **asr**: sends audio to faster-whisper for transcription.
- **answer**: streams LLM response, plays TTS, updates display incrementally.
- **image**: shows a generated image; button press returns to `listening`.

State handlers are plain functions — they register button/text callbacks and call `display()`. `transitionTo()` in `ChatFlow` also calls `display({ text_input_enabled: flowName === "sleep" })` on every transition.

### Plugin / provider system

ASR, LLM, and TTS are swappable via `.env` (`ASR_SERVER`, `LLM_SERVER`, `TTS_SERVER`). Each provider is registered in `src/plugin/` and selected at runtime by `src/cloud-api/server.ts`. External plugins can be dropped into a `plugins/` directory or installed as npm packages prefixed `whisplay-plugin-`.

### Python LCD layer

`python/chatbot-ui.py` runs two threads:
- **RenderThread** — draws frames to the LCD at 30 fps. Handles image mode, text scrolling with sync, animation frames (loaded from `python/animations/<state>/`), header (emoji, status, battery/wifi/VPN icons), and music progress bar.
- **Socket server thread** — accepts JSON commands from Node, updates global display state, fires button/camera events back.

`whisplay.cleanup()` must be called on exit to turn off the backlight and release GPIO/SPI. The `finally` block in `start_socket_server` calls it on SIGINT/KeyboardInterrupt. `stop_chatbot.sh` sends SIGINT to `chatbot-ui.py` to trigger this path cleanly.

### Display status fields

The `Status` interface (`src/device/display.ts`) is the contract between Node and Python. Key fields:
- `status` / `emoji` — shown in the header; `status` also drives animation frame selection
- `text` — main scrolling body text; supports `{count}` for a live elapsed-second counter
- `brightness` — 0–100; every `display()` call resets to 100 unless overridden
- `RGB` — hex color for the RGB LED (e.g. `"#00FF30"`)
- `image` — path to an image file to fullscreen on the LCD; set to `""` to return to text mode
- `camera_mode` — boolean, hands LCD over to the camera thread

### Key env variables

| Variable | Purpose |
|---|---|
| `WHISPLAY_DEVICE_ENABLED` | Set to `false` to run without physical hardware |
| `WHISPLAY_WEB_ENABLED` + `WEB_AUDIO_ENABLED` | Browser-based mic/speaker for dev on laptop |
| `SERVE_OLLAMA` / `SERVE_FASTER_WHISPER` | Auto-start local model servers |
| `ENABLE_RAG` | Toggle retrieval-augmented generation |
| `RAG_KNOWLEDGE_SCORE_THRESHOLD` | Qdrant similarity cutoff (0.0–1.0, default 0.8) |
| `SYSTEM_PROMPT` | LLM personality/instructions |
| `WAKE_WORD_ENABLED` | Enable always-on wake word listening |
| `WHISPLAY_ADMIN_PORT` | Enable browser admin UI |

### Adding an LLM tool (function calling)

Copy `src/config/custom-tools/template.ts`, implement the tool, then register it in `src/plugin/builtin/llm-tools.ts`. Rebuild after.
