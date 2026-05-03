# Solarbot

A feminist AI voice chatbot for Raspberry Pi (Zero 2W or Pi 5), built around a project knowledge base. Press the button, speak, get a short spoken answer. Powered by local-first models — no cloud required.

**Stack:** faster-whisper (ASR) · ollama (LLM) · piper (TTS) · qdrant + ollama-embeddings (RAG)

---

## Hardware

- Raspberry Pi Zero 2W or Pi 5
- PiSugar Whisplay HAT (LCD 240×280, speaker, mic, RGB LED, button)
- PiSugar 3 battery

---

## Install

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/solarbot.git ~/solarbot
cd ~/solarbot
```

### 2. Install system dependencies

```bash
bash install_dependencies.sh
```

This installs Node.js 20, Python packages, and fonts.

### 3. Install Ollama

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:0.5b          # LLM
ollama pull nomic-embed-text      # embeddings for RAG
```

### 4. Install Piper TTS

```bash
pip install piper-tts --break-system-packages
# Download a voice model
python3 -m piper.download_voices en_US-amy-medium
```

The model will land in `~/piper/`. Note the path — you'll set it in `.env`.

### 5. Set up the faster-whisper service

Either run it via Docker (easiest):

```bash
cd docker
docker compose up -d faster-whisper
cd ..
```

Or install it directly:

```bash
pip install faster-whisper --break-system-packages
python3 python/speech-service/faster-whisper-host.py &
```

### 6. Start Qdrant (vector database for RAG)

```bash
cd docker
docker compose up -d   # starts qdrant (and ollama/piper if you prefer docker for those too)
cd ..
```

Or run qdrant standalone:

```bash
docker run -d -p 6333:6333 qdrant/qdrant
```

### 7. Configure

```bash
cp .env.template .env
```

Edit `.env` — the two lines you must change for your machine:

```env
PIPER_BINARY_PATH=/home/pi/.local/bin/piper         # where piper binary lives
PIPER_MODEL_PATH=/home/pi/piper/en_US-amy-medium.onnx  # voice model path
```

Everything else works out of the box with the defaults.

### 8. Build and run

```bash
npm install
npm run build
bash run_chatbot.sh
```

---

## Run

```bash
bash run_chatbot.sh
```

Or after the first build:

```bash
npm start
```

**To run as a background service** (auto-starts on boot):

```bash
bash startup.sh
```

View logs:

```bash
tail -f ~/solarbot/chatbot.log
```

---

## Knowledge Base (RAG)

Drop any `.txt`, `.md`, or `.pdf` files into the `knowledge/` folder, then index them:

```bash
npm run index-knowledge
```

The bot will automatically use relevant knowledge when answering questions. The `RAG_KNOWLEDGE_SCORE_THRESHOLD` in `.env` (default `0.8`) controls how confident the match needs to be before it's used — lower it to retrieve more loosely related content.

---

## Dev mode (no hardware)

Run the chatbot on your laptop with a browser-based mic and speaker:

```env
# .env
WHISPLAY_WEB_ENABLED=true
WHISPLAY_WEB_PORT=17880
WEB_AUDIO_ENABLED=true
```

Then open `http://localhost:17880` after starting the bot. The browser handles audio input/output.

---

## Admin UI

A browser-based admin panel lets you upload knowledge files, trigger reindexing, and edit `.env` config without touching the Pi over SSH.

Enable it by adding to `.env`:

```env
WHISPLAY_ADMIN_PORT=18780
ADMIN_TOKEN=your_secret_token   # recommended if exposing externally
```

Then open `http://<pi-ip>:18780`. To share it over the internet, tunnel the port with cloudflared:

<!--```bash
cloudflared tunnel --url http://localhost:18780
```-->

---

## Making changes

### Change the personality / system prompt

Edit `SYSTEM_PROMPT` in `.env`:

```env
SYSTEM_PROMPT="You are sun shines, a feminist AI companion, you can access a  project knowledge base with a few feminist texts.
Answer in short 1-2 sentences only.
Use an intersectional feminist lens: prioritize care, justice, lived experiences. 
Use RAG context when available."
```

No rebuild needed — restarts pick up the new prompt.

### Change the LLM model

```bash
ollama pull qwen2.5:1.5b   # or any model at ollama.com/library
```

Then update `.env`:

```env
OLLAMA_MODEL=qwen2.5:1.5b
```

### Change the voice

Download a different Piper voice:

```bash
python3 -m piper.download_voices en_GB-alba-medium
```

Then update `.env`:

```env
PIPER_MODEL_PATH=/home/pi/piper/en_GB-alba-medium.onnx
```

Browse voices at [rhasspy.github.io/piper-samples](https://rhasspy.github.io/piper-samples/).

### Add a custom LLM tool (function calling)

Create a file in `src/config/custom-tools/` using the template at `src/config/custom-tools/template.ts`, then register it in `src/plugin/builtin/llm-tools.ts`.

Rebuild after TypeScript changes:

```bash
npm run build
```

### Adjust RAG sensitivity

In `.env`:

```env
RAG_KNOWLEDGE_SCORE_THRESHOLD=0.75   # lower = retrieve more (less strict)
```

Range is 0.0–1.0. Re-index after changing the knowledge files, not just the threshold.

---

## Project structure

```
solarbot/
├── src/
│   ├── index.ts                    # entry point
│   ├── cloud-api/local/            # faster-whisper, ollama, piper, qdrant
│   ├── core/                       # chat flow state machine
│   ├── device/                     # audio, display, button
│   ├── config/                     # system prompt, LLM tools
│   ├── plugin/                     # plugin registry (asr/llm/tts)
│   └── utils/                      # text helpers, dir paths
├── python/                         # hardware interface (GPIO, LCD, socket)
├── knowledge/                      # drop your .txt/.md/.pdf files here
├── docker/                         # faster-whisper, piper, qdrant services
├── .env.template                   # copy to .env and edit
└── data/                           # runtime audio, embeddings (auto-created)
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| No audio output | Run `amixer` and check WM8960 driver: `lsmod \| grep wm8960` |
| Display not updating | Check socket on port 12345: `ss -tlnp \| grep 12345` |
| ASR not working | Check faster-whisper is running: `curl http://localhost:8803/health` |
| Qdrant not reachable | Check docker: `docker ps \| grep qdrant` |
| Build errors | Run `npm install` then `npm run build` and read the TS errors |

---

## License

GPL-3.0
