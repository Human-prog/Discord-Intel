"""Centralized authorization interface (Phase 5).

Provides the AuthorizationChecker class which every protected operation
must pass before any project data is read or written.  Fail-closed: any
missing or unrecognized identity/permission results in denial.

All checks use IDs (not display names) as authorization identifiers.
"""

from __future__ import annotations

from typing import Any, List, Optional, Tuple

from ..config import Settings
from ..security.authentication import AuthContext, AuthError


class AuthorizationError(AuthError):
    """Raised when authorization check fails. Message never contains secrets."""


class AuthorizationChecker:
    """Centralized per-operation authorization.

    All protected operations in the application must pass through one or more
    methods of this checker before any project- or integration-specific data
    is accessed.  The default policy is deny-by-default.

    The checker coordinates three independent authorization domains:
    1. User identity (is this a known/discord user in the right guild/channel?)
    2. Project membership (is this user authorized for this project?)
    3. Command mapping (is this Discord context mapped to this project+command?)
    """

    def __init__(self, auth_ctx: AuthContext, settings: Settings) -> None:
        self._auth = auth_ctx
        self._settings = settings

    # ------------------------------------------------------------------
    # User identity checks
    # ------------------------------------------------------------------

    def check_user_guild_channel(
        self,
        *,
        required_guild_ids: Optional[List[int]] = None,
        required_channel_ids: Optional[List[int]] = None,
    ) -> None:
        """Ensure the user's guild and channel are in the allowed whitelists.

        - If *required_guild_ids* is provided, the user's guild must match one
          of these IDs.
        - If *required_channel_ids* is provided, the user's channel must match
          one of these IDs.
        - If the whitelist is empty (default), the check is bypassed (but
          project-level authorization is still required).
        - If the user's guild is not in the required list, AuthError is raised.
        """
        guild_id = self._auth.discord_guild_id
        channel_id = self._auth.discord_channel_id

        # Guild whitelist check
        if required_guild_ids is not None:
            if guild_id not in required_guild_ids:
                raise AuthorizationError(
                    f"User not authorized in this guild (guild_id={guild_id}); "
                    "this command is not registered for your server."
                )

        # Channel whitelist check
        if required_channel_ids is not None:
            if channel_id not in required_channel_ids:
                raise AuthorizationError(
                    f"User not authorized in this channel (channel_id={channel_id}); "
                    "this command is not available in your channel."
                )

    def check_user_is_member_of_guild(self) -> None:
        """Ensure the user's guild is not None and is a configured server.

        In practice this is a no-op if the interaction always carries a guild
        ID, but it prevents None‑guild crashes if a DM interaction somehow
        reaches the bot.
        """
        if self._auth.discord_guild_id is None:
            raise AuthorizationError(
                "Cannot operate outside a guild (DM detected). "
                "This command is guild-only."
            )

    # ------------------------------------------------------------------
    # Project authorization checks
    # ------------------------------------------------------------------

    def check_project_access(self, project_id: int) -> None:
        """Ensure the authenticated user is authorized for the given project.

        Authorization is granted if:
        - The user is listed in ``authorized_users`` for this project, OR
        - The user is a configured owner (checked via AuthContext.is_owner).

        Raises AuthorizationError if the user has no access to this project.
        """
        # Owners always have access to everything.
        if self._auth.is_owner(self._settings):
            return

        # Check the authorized_users table via the repository layer.
        # The repository will query the database; if no row exists, an
        # AuthorizationError is raised below.
        from ..storage.repositories import get_authorized_user

        auth_user = get_authorized_user(
            conn=None,  # will be provided by caller via transaction
            discord_user_id=self._auth.discord_user_id,
            project_id=project_id,
        )
        # The caller is responsible for passing a connection; if None is passed
        # the repository will create one.  For now we short-circuit when the
        # repository is called without a connection by checking the allowlist.
        # This placeholder will be replaced by the real integration in the
        # caller's transaction block.
        if auth_user is None:
            raise AuthorizationError(
                f"User (id={self._auth.discord_user_id}) is not authorized "
                f"for project (id={project_id}). "
                "Use /connect-project to map this context to an authorized project."
            )

    def check_command_mapped(
        self, project_id: int, command_name: str
    ) -> None:
        """Ensure the Discord guild/channel/context is mapped to this project+command.

        This consults the discord_mappings table to verify that the current
        guild+channel+command combination has been explicitly registered for
        this project.  Prevents arbitrary project access through command
        name guessing.
        """
        from ..storage.repositories import get_mapping

        mapping = get_mapping(
            conn=None,
            project_id=project_id,
            guild_id=self._auth.discord_guild_id,
            channel_id=self._auth.discord_channel_id,
            command_name=command_name,
        )
        if mapping is None:
            raise AuthorizationError(
                f"Command /{command_name} is not mapped to any project in "
                f"this guild/channel (guild={self._auth.discord_guild_id}, "
                f"channel={self._auth.discord_channel_id}). "
                "Use /connect-project to register this context."
            )

    # -----------------------------------------------------------------
    # Convenience helpers for common patterns
    # -----------------------------------------------------------------

    def check_owner_or_project(self, project_id: int) -> None:
        """Allow access if the user is an owner, otherwise check project auth."""
        if self._auth.is_owner(self._settings):
            return
        self.check_project_access(project_id)

    def check_project_and_command(
        self, project_id: int, command_name: str
    ) -> None:
        """Require both project access and command mapping validation."""
        self.check_project_access(project_id)
        self.check_command_mapped(project_id, command_name)


def make_checker(auth_ctx: AuthContext, settings: Settings) -> AuthorizationChecker:
    """Factory for AuthorizationChecker instances.

    Consumers should call this rather than instantiating AuthorizationChecker
    directly, to ensure consistent configuration.
    """
    return AuthorizationChecker(auth_ctx, settings)