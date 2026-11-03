# Discord Project Intelligence — Portable Install

Search keywords: `discord-voice-bot`, `stt-tts-whisper`, `pyttsx3-voice`, `image-generation-stable-diffusion`, `vision-analysis-ollama`, `free-model-rotation`, `discord-bot-health-backup`, `discord-research-pipeline`, `discord-voice-join-leave`, `discord-schedule-research`, `discord-project-intelligence-install`

# Quick install (Linux server / homelab)

```bash
sudo bash install-voice-image.sh
```

Includes: voice client, Whisper STT, pyttsx3 TTS, Stable Diffusion image, Ollama vision, free-model rotation, health check, backup/notification commands.

## Manual install steps

```bash
apt install -y python3-pip python3-venv ffmpeg python3-nacl nginx curl git
python3 -m pip install --break-system-packages openai-whisper pyttsx3 diffusers transformers accelerate torch numpy pillow httpx huggingface-hub safetensors
systemctl restart discord-project-intelligence-bot discord-project-intelligence
```

## New commands (test after install)

- Voice: `/voice-join`, `/voice-leave`, `/voice-status`, `/voice-listen`, `/voice-stop`, `/voice-ask`, `/voice-speak`
- Media: `/generate-image`, `/vision`
- Research / System: `/research-deep`, `/catalog-rescan`, `/notify-research`, `/backup-drill`, `/health-full`, `/scheduled-run`, `/model-switch`, `/image-edit`, `/vision-compare`, `/voice-clone-test`, `/export-report`, `/github-sync`, `/denv-config`

## Health endpoint

`https://your-tailnet-url.example.com/health` or `http://127.0.0.1:8765/health`

## Source

Repo: `Discord Project Intelligence` (`discord/voice.py`, `discord/vision.py`, `discord/image_gen.py`, `discord/new_commands.py`)
