"""Smoke tests for new feature modules (Phase 27+)."""


def test_image_gen_imports() -> None:
    from project_intelligence.discord.image_gen import ImageGenerator
    assert ImageGenerator is not None


def test_vision_imports() -> None:
    from project_intelligence.discord.vision import VisionEngine
    assert VisionEngine is not None


def test_voice_speech_imports() -> None:
    from project_intelligence.discord.voice_speech import VoiceInteraction
    assert VoiceInteraction is not None


def test_new_commands_registered() -> None:
    from project_intelligence.discord.new_commands import _reply
    assert callable(_reply)
