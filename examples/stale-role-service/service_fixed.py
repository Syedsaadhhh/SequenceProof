"""Role authorization service — corrected implementation.

Fix: the role cache is updated on every account switch, so the
authorized role always reflects the current account.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuthState:
    """Mutable authorization state for one session."""
    current_user: str | None = None
    _role_cache: str | None = None

    def switch_account(self, username: str, role: str) -> None:
        """Switch to a different account and immediately refresh the role."""
        self.current_user = username
        self._role_cache = role  # Always update — fix for the stale-snapshot bug.

    def get_authorized_role(self) -> str | None:
        """Return the role for the current account."""
        return self._role_cache

    def perform_action(self, action: str) -> dict[str, Any]:
        """Perform a privileged action; returns result with authorized role."""
        if self.current_user is None:
            raise ValueError("no account active")
        authorized_as = self.get_authorized_role()
        return {
            "action": action,
            "user": self.current_user,
            "authorized_as": authorized_as,
        }
