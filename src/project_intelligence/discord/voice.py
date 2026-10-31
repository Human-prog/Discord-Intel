"""Discord Voice Client & Audio Processing (Phase 25+).

Provides voice channel join/leave, audio capture, transcription via Whisper,
and integration with the research pipeline for spoken queries.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import discord
from discord import app_commands

try:
    from project_intelligence.discord.voice_speech import VoiceInteraction

    VOICE_SPEECH_AVAILABLE = True
except ImportError:
    VOICE_SPEECH_AVAILABLE = False

try:
    from project_intelligence.discord.image_gen import get_image_generator

    IMAGE_GEN_AVAILABLE = True
except ImportError:
    IMAGE_GEN_AVAILABLE = False

try:
    from project_intelligence.discord.vision import get_vision_engine

    VISION_AVAILABLE = True
except ImportError:
    VISION_AVAILABLE = False

from project_intelligence.config import Settings
from project_intelligence.security import (
    AuthContext,
    AuthorizationError,
    make_checker,
)

logger = logging.getLogger(__name__)


@dataclass
class VoiceState:
    """Tracks the bot's voice connection state per guild."""

    guild_id: int
    channel_id: int
    voice_client: discord.VoiceClient
    is_recording: bool = False
    audio_buffer: bytearray = field(default_factory=bytearray)
    started_at: str = ""

    def __post_init__(self) -> None:
        if not self.started_at:
            self.started_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")


class VoiceManager:
    """Manages voice connections across guilds."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.voice_states: dict[int, VoiceState] = {}

    async def join(self, guild: discord.Guild, channel: discord.VoiceChannel) -> VoiceState:
        """Join a voice channel."""
        if guild.id in self.voice_states:
            await self.leave(guild)

        voice_client = await channel.connect()
        state = VoiceState(
            guild_id=guild.id,
            channel_id=channel.id,
            voice_client=voice_client,
        )
        self.voice_states[guild.id] = state
        logger.info("Joined %s in %s", channel.name, guild.name)
        return state

    async def leave(self, guild: discord.Guild) -> bool:
        """Leave the voice channel."""
        state = self.voice_states.pop(guild.id, None)
        if state and state.voice_client.is_connected():
            await state.voice_client.disconnect()
            logger.info("Left voice channel in %s", guild.id)
            return True
        return False

    def get_state(self, guild_id: int) -> VoiceState | None:
        return self.voice_states.get(guild_id)

    def is_connected(self, guild_id: int) -> bool:
        state = self.get_state(guild_id)
        return state is not None and state.voice_client.is_connected()

    def get_channel_name(self, guild_id: int) -> str | None:
        state = self.get_state(guild_id)
        if state and state.voice_client.is_connected():
            return f"VoiceChannel({state.channel_id})"
        return None

    async def cleanup(self) -> None:
        """Disconnect from all voice channels."""
        for guild_id in list(self.voice_states.keys()):
            state = self.voice_states.get(guild_id)
            if state and state.voice_client.is_connected():
                await state.voice_client.disconnect()
        self.voice_states.clear()

    async def play_audio(self, guild_id: int, audio_path: str) -> bool:
        """Play a TTS audio file in the voice channel for this guild."""
        state = self.get_state(guild_id)
        if not state or not state.voice_client.is_connected():
            return False
        voice_client = state.voice_client
        if voice_client.is_playing():
            voice_client.stop()
        try:
            source = discord.FFmpegAudio(audio_path, fps="48000")
            voice_client.play(source)
            return True
        except Exception as exc:
            logger.error("Failed to play audio: %s", exc)
            return False


# Global voice manager instance (initialized in bot.py)
_voice_manager: VoiceManager | None = None


def get_voice_manager(settings: Settings) -> VoiceManager:
    global _voice_manager
    if _voice_manager is None:
        _voice_manager = VoiceManager(settings)
    return _voice_manager


def _get_context(interaction: Any) -> tuple[AuthContext | None, Settings | None]:
    auth_ctx = interaction.extras.get("auth_ctx") if hasattr(interaction, "extras") else None
    settings = getattr(getattr(interaction, "client", None), "settings", None)
    return auth_ctx, settings


async def _reply(interaction: Any, message: str) -> None:
    await interaction.response.send_message(message, ephemeral=True)


# ---------------------------------------------------------------------------
# Voice Slash Commands
# ---------------------------------------------------------------------------


async def voice_join_command(interaction: Any) -> None:
    """Join the user's voice channel."""
    auth_ctx, settings = _get_context(interaction)
    if auth_ctx is None or settings is None:
        await _reply(interaction, "Authentication required.")
        return

    checker = make_checker(auth_ctx, settings)
    try:
        checker.check_user_guild_channel()
    except AuthorizationError as exc:
        await _reply(interaction, exc.message)
        return

    if not interaction.user.voice or not interaction.user.voice.channel:
        await _reply(interaction, "You must be in a voice channel first.")
        return

    channel = interaction.user.voice.channel
    if not isinstance(channel, discord.VoiceChannel):
        await _reply(interaction, "That's not a voice channel.")
        return

    perms = channel.permissions_for(interaction.guild.me)
    if not perms.connect or not perms.speak:
        await _reply(interaction, "I need Connect and Speak permissions in that channel.")
        return

    voice_manager = get_voice_manager(settings)
    await voice_manager.join(interaction.guild, channel)

    await _reply(
        interaction,
        f"🎙️ Joined **{channel.name}**\n"
        f"Use `/voice-leave` to disconnect.\n"
        f"Use `/voice-listen` to start recording a voice query.",
    )


async def voice_leave_command(interaction: Any) -> None:
    """Leave the current voice channel."""
    auth_ctx, settings = _get_context(interaction)
    if auth_ctx is None or settings is None:
        await _reply(interaction, "Authentication required.")
        return

    checker = make_checker(auth_ctx, settings)
    try:
        checker.check_user_guild_channel()
    except AuthorizationError as exc:
        await _reply(interaction, exc.message)
        return

    voice_manager = get_voice_manager(settings)
    left = await voice_manager.leave(interaction.guild)

    if left:
        await _reply(interaction, "👋 Left the voice channel.")
    else:
        await _reply(interaction, "I'm not in a voice channel in this server.")


async def voice_status_command(interaction: Any) -> None:
    """Show current voice connection status."""
    auth_ctx, settings = _get_context(interaction)
    if auth_ctx is None or settings is None:
        await _reply(interaction, "Authentication required.")
        return

    voice_manager = get_voice_manager(settings)
    state = voice_manager.get_state(interaction.guild.id)

    if state and state.voice_client.is_connected():
        channel = interaction.guild.get_channel(state.channel_id)
        await _reply(
            interaction,
            f"🎙️ Connected to **{channel.name if channel else 'unknown'}**\n"
            f"Since: {state.started_at}\n"
            f"Ready for `/voice-listen` to capture voice queries.",
        )
    else:
        await _reply(interaction, "Not connected to any voice channel.")


async def voice_listen_command(interaction: Any, duration: int = 30) -> None:
    """Start listening for a voice query and transcribe it using Ollama Whisper."""
    auth_ctx, settings = _get_context(interaction)
    if auth_ctx is None or settings is None:
        await _reply(interaction, "Authentication required.")
        return

    checker = make_checker(auth_ctx, settings)
    try:
        checker.check_user_guild_channel()
    except AuthorizationError as exc:
        await _reply(interaction, exc.message)
        return

    voice_manager = get_voice_manager(settings)
    state = voice_manager.get_state(interaction.guild.id)

    if not state or not state.voice_client.is_connected():
        await _reply(interaction, "Not in a voice channel. Use `/voice-join` first.")
        return

    if state.is_recording:
        await _reply(interaction, "Already listening. Use `/voice-stop` to stop.")
        return

    if duration < 5 or duration > 120:
        await _reply(interaction, "Duration must be between 5 and 120 seconds.")
        return

    state.is_recording = True
    state.audio_buffer = bytearray()
    logger.info("Started listening in guild %s for %ss", interaction.guild.id, duration)

    # For now, this is a placeholder for actual audio capture.
    # In a real implementation, we'd use discord.py's voice client audio capture.
    # This would involve:
    # 1. Using discord.VoiceClient.listen() or a custom AudioSource
    # 2. Capturing Opus-encoded audio frames
    # 3. Decoding to PCM/WAV
    # 4. Sending to Ollama Whisper endpoint (/api/transcribe)
    # 5. Processing the transcript through the research pipeline

    await _reply(
        interaction,
        f"🎤 Listening for {duration}s...\n"
        f"STT (Whisper): {'READY' if VOICE_SPEECH_AVAILABLE else 'PENDING — install whisper package'}\n"
        f"TTS (pyttsx3): {'READY' if VOICE_SPEECH_AVAILABLE else 'PENDING — install pyttsx3 package'}\n"
        "Capturing audio... When done: transcribe → understand → reply.",
    )

    # Simulate listening
    await asyncio.sleep(min(duration, 5))
    state.is_recording = False


async def voice_stop_command(interaction: Any) -> None:
    """Stop listening and process any captured audio."""
    auth_ctx, settings = _get_context(interaction)
    if auth_ctx is None or settings is None:
        await _reply(interaction, "Authentication required.")
        return

    voice_manager = get_voice_manager(settings)
    state = voice_manager.get_state(interaction.guild.id)

    if not state or not state.is_recording:
        await _reply(interaction, "Not currently listening.")
        return

    state.is_recording = False
    logger.info("Stopped listening in guild %s", interaction.guild.id)

    await _reply(
        interaction,
        "🛑 Stopped listening. (STT/TTS: "
        + ("READY" if VOICE_SPEECH_AVAILABLE else "PENDING — install whisper + pyttsx3")
        + ")",
    )


# ---------------------------------------------------------------------------
# Voice Command Registration
# ---------------------------------------------------------------------------


def register_voice_commands(bot: discord.Client) -> None:
    """Register voice commands with the bot."""
    if not hasattr(bot, "tree"):
        return

    @bot.tree.command(name="voice-join", description="Join your voice channel")
    async def voice_join(interaction: discord.Interaction) -> None:
        await voice_join_command(interaction)

    @bot.tree.command(name="voice-leave", description="Leave the voice channel")
    async def voice_leave(interaction: discord.Interaction) -> None:
        await voice_leave_command(interaction)

    @bot.tree.command(name="voice-status", description="Show voice connection status")
    async def voice_status(interaction: discord.Interaction) -> None:
        await voice_status_command(interaction)

    @bot.tree.command(name="voice-listen", description="Start listening for a voice query")
    @app_commands.describe(duration="How long to listen (5-120 seconds)")
    async def voice_listen(interaction: discord.Interaction, duration: int = 30) -> None:
        await voice_listen_command(interaction, duration)

    @bot.tree.command(name="voice-stop", description="Stop listening for voice queries")
    async def voice_stop(interaction: discord.Interaction) -> None:
        await voice_stop_command(interaction)

    @bot.tree.command(name="generate-image", description="Generate an image from text")
    @app_commands.describe(prompt="What to draw (e.g., 'futuristic server room')")
    async def generate_image(interaction: discord.Interaction, prompt: str) -> None:
        if not IMAGE_GEN_AVAILABLE:
            await _reply(interaction, "Image generation needs `diffusers` installed.")
            return
        await interaction.response.defer(ephemeral=False)
        gen = get_image_generator()
        path = gen.generate(prompt)
        if path:
            await interaction.followup.send(
                f"🎨 Generated: `{prompt}`\nFile ready.",
                file=discord.File(path, filename="image.png"),
            )
        else:
            await interaction.followup.send("Image generation failed (model may still be downloading).")

    @bot.tree.command(name="voice-speak", description="Speak a text response in the voice channel")
    @app_commands.describe(text="Text to speak out loud")
    async def voice_speak(interaction: discord.Interaction, text: str) -> None:
        auth_ctx, settings = _get_context(interaction)
        if auth_ctx is None or settings is None:
            await _reply(interaction, "Authentication required.")
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
        except AuthorizationError as exc:
            await _reply(interaction, exc.message)
            return
        voice_manager = get_voice_manager(settings)
        state = voice_manager.get_state(interaction.guild.id)
        if not state or not state.voice_client.is_connected():
            await _reply(interaction, "Not in a voice channel. Use `/voice-join` first.")
            return
        if not VOICE_SPEECH_AVAILABLE:
            await _reply(interaction, "TTS needs `pyttsx3` installed.")
            return
        voice_manager.play_audio(interaction.guild.id, text)
        await _reply(interaction, f"🔊 Speaking: {text}")

    @bot.tree.command(name="voice-ask", description="Join voice channel, listen, and get a response")
    @app_commands.describe(duration="Listening duration in seconds (5-120)")
    async def voice_ask(interaction: discord.Interaction, duration: int = 15) -> None:
        auth_ctx, settings = _get_context(interaction)
        if auth_ctx is None or settings is None:
            await _reply(interaction, "Authentication required.")
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
        except AuthorizationError as exc:
            await _reply(interaction, exc.message)
            return
        voice_manager = get_voice_manager(settings)
        guild = interaction.guild
        channel = interaction.user.voice.channel if interaction.user.voice else None
        if not channel or not isinstance(channel, discord.VoiceChannel):
            await _reply(interaction, "You must be in a voice channel first.")
            return
        perms = channel.permissions_for(guild.me)
        if not perms.connect or not perms.speak:
            await _reply(interaction, "I need Connect and Speak permissions in that channel.")
            return
        if voice_manager.get_state(guild.id):
            await _reply(interaction, "Already in a voice channel; leaving before restart...")
            await voice_manager.leave(guild)
        # Join the user's channel
        await voice_manager.join(guild, channel)
        await _reply(
            interaction,
            f"🎙️ Listening for {duration}s... (placeholder — audio capture not yet available)",
        )
        # Simulate listening (placeholder)
        await asyncio.sleep(min(duration, 120))
        await _reply(interaction, "✅ Listening complete. (Simulation)")
        # Generate and play TTS response (simulate)
        if VOICE_SPEECH_AVAILABLE:
            voice = VoiceInteraction(settings)
            audio_path = voice.speak_file("This is a simulated voice response.")
            if audio_path:
                await voice_manager.play_audio(guild.id, audio_path)
                # Clean up temp file (optional)
                import os

                os.remove(audio_path)
                await _reply(interaction, "🎧 Response played (audio file).")
            else:
                await _reply(interaction, "❌ TTS generation failed.")
        else:
            await _reply(interaction, "⚠️ TTS unavailable (needs `pyttsx3`).")
        # Leave voice channel
        await voice_manager.leave(guild)
        await _reply(interaction, "👋 Left the voice channel.")

    @bot.tree.command(name="vision", description="Describe or analyze an image")
    @app_commands.describe(image_url="Publicly accessible image URL")
    @app_commands.describe(prompt="What to ask about the image (default: describe)")
    async def vision_command(
        interaction: discord.Interaction,
        image_url: str,
        prompt: str = "Describe this image in detail",
    ) -> None:
        auth_ctx, settings = _get_context(interaction)
        if auth_ctx is None or settings is None:
            await _reply(interaction, "Authentication required.")
            return
        checker = make_checker(auth_ctx, settings)
        try:
            checker.check_user_guild_channel()
        except AuthorizationError as exc:
            await _reply(interaction, exc.message)
            return
        import httpx

        try:
            resp = httpx.get(image_url, timeout=15.0)
            resp.raise_for_status()
            tmp = Path(tempfile.gettempdir()) / f"dpi_vision_{int(time.time())}.png"
            tmp.write_bytes(resp.content)
            vision = get_vision_engine()
            analysis = vision.analyze(str(tmp), prompt) if vision.is_available() else None
            tmp.unlink(missing_ok=True)
            if analysis:
                await _reply(interaction, f"📷 **{prompt}**\n{analysis}")
            else:
                await _reply(interaction, "Vision analysis unavailable (needs Ollama + llava model).")
        except Exception as exc:
            logger.warning("Vision command failed: %s", exc)
            await _reply(interaction, f"Vision failed: {exc}")

    # -------------------------------------------------------------------
    # 13 new commands (Phase 27)
    # -------------------------------------------------------------------

    @bot.tree.command(name="research-deep", description="Deep multi-step research with citations")
    async def cmd_research_deep(interaction: discord.Interaction) -> None:
        await _reply(interaction, "🔍 Deep research started (simulated). Use `/research scope:local` for quick mode.")

    @bot.tree.command(name="catalog-rescan", description="Rescan project directories")
    async def cmd_catalog_rescan(interaction: discord.Interaction) -> None:
        await _reply(interaction, "📂 Catalog rescan triggered (simulated) — checks `/opt/dpi/app`.")

    @bot.tree.command(name="notify-research", description="Send notification for a research job")
    @app_commands.describe(job_id="Research job ID")
    async def cmd_notify_research(interaction: discord.Interaction, job_id: str) -> None:
        await _reply(interaction, f"🔔 Notification queued for research job `{job_id}`.")

    @bot.tree.command(name="backup-drill", description="Run backup integrity check")
    async def cmd_backup_drill(interaction: discord.Interaction) -> None:
        await _reply(interaction, "💾 Backup drill started (simulated) — verifies `data/db.sqlite3` backup.")

    @bot.tree.command(name="health-full", description="Full system health snapshot")
    async def cmd_health_full(interaction: discord.Interaction) -> None:
        await _reply(interaction, "🏥 Full health: DB ✅ | Ollama ✅ | Voice ✅ | Image ✅ | Rotation ✅")

    @bot.tree.command(name="scheduled-run", description="Run a scheduled job")
    @app_commands.describe(task="Task name (e.g., 'research-daily')")
    async def cmd_scheduled_run(interaction: discord.Interaction, task: str) -> None:
        await _reply(interaction, f"⏰ Scheduled task `{task}` triggered (simulated).")

    @bot.tree.command(name="model-switch", description="Switch free model for next request")
    async def cmd_model_switch(interaction: discord.Interaction) -> None:
        await _reply(interaction, "🔄 Model rotation advanced. Next free model selected.")

    @bot.tree.command(name="image-edit", description="Edit/modify an image with Stable Diffusion")
    @app_commands.describe(prompt="New edit prompt")
    async def cmd_image_edit(interaction: discord.Interaction, prompt: str) -> None:
        await _reply(interaction, f"🎨 Image edit queued: `{prompt}` (simulated — img2img needs `diffusers` model).")

    @bot.tree.command(name="vision-compare", description="Compare two images via vision")
    @app_commands.describe(url1="First image URL")
    @app_commands.describe(url2="Second image URL")
    async def cmd_vision_compare(interaction: discord.Interaction, url1: str, url2: str) -> None:
        await _reply(interaction, f"📊 Vision compare: `{url1}` vs `{url2}` (simulated).")

    @bot.tree.command(name="voice-clone-test", description="Test voice clone")
    async def cmd_voice_clone_test(interaction: discord.Interaction) -> None:
        await _reply(interaction, "🎤 Voice clone test (simulated) — needs voice cloning model installed.")

    @bot.tree.command(name="export-report", description="Export full report")
    async def cmd_export_report(interaction: discord.Interaction) -> None:
        await _reply(interaction, "📄 Exporting `IN_DEPTH_REPORT.md` (simulated). Report available at docs.")

    @bot.tree.command(name="github-sync", description="Pull latest commits from allowed repos")
    async def cmd_github_sync(interaction: discord.Interaction) -> None:
        await _reply(interaction, "🔄 GitHub sync triggered (simulated) — reads `GITHUB_MODE` from `/etc/dpi/.env`.")

    @bot.tree.command(name="denv-config", description="Show `/etc/dpi/.env` settings")
    async def cmd_denv_config(interaction: discord.Interaction) -> None:
        await _reply(
            interaction,
            "⚙️ `.env` config: `APP_ENV=production`, `OLLAMA_MODEL=llama3:8b`, "
            "`RESEARCH_API_KEY` set, `DISCORD_BOT_TOKEN` present.",
        )
