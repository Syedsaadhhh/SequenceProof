"""Role authorization service — buggy implementation.

Bug: after an account switch, the service still uses the role cached
from the previous account (stale snapshot). The role is never refreshed.

This file is the implementation used for bug reproduction.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AuthState:
    """Mutable authorization state for one session."""
    current_user: str | None = None
    _role_cache: str | None = None  # Stale snapshot — the bug.

    def switch_account(self, username: str, role: str) -> None:
        """Switch to a different account.

        Bug: the role is cached at switch time and never cleared
        when a subsequent switch_account is called.
        """
        self.current_user = username
        if self._role_cache is None:
            # Only populate the cache on the FIRST switch — never update it.
            self._role_cache = role

    def get_authorized_role(self) -> str | None:
        """Return the role that will actually be used for authorization.

        Bug: returns the stale cached role from the first switch, not
        the role for the current account.
        """
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
