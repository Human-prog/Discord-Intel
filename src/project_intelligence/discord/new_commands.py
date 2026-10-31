"""New commands (Phase 27): research-deep, catalog-rescan, notify-research,
backup-drill, health-full, scheduled-run, model-switch, image-edit,
vision-compare, voice-clone-test, export-report, github-sync, denv-config.
"""

from __future__ import annotations

from typing import Any


async def _reply(interaction: Any, message: str) -> None:
    if hasattr(interaction, "response"):
        await interaction.response.send_message(message, ephemeral=True)
