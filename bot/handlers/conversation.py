"""Conversation handler — main wizard flow.

States:
    CHOOSE  — user picks /steam, /itch, or /mixed
    COLLECT — user pastes links (or uploads file); /done to advance
    CONFIRM — preview shown; /yes to dispatch, /cancel to abort

Phase 0: state constants + builder skeleton.
Phase 1: full handlers (collect, done, yes, cancel) wired with classifier + dispatcher.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from telegram.ext import ConversationHandler


# Conversation states (used by ConversationHandler)
CHOOSE = 0
COLLECT = 1
CONFIRM = 2


def build_conversation_handler() -> ConversationHandler:
    """Construct the ConversationHandler with all entry/state/fallback handlers.

    TODO(phase-1): wire up start, choose, collect, done, yes, cancel handlers.
    """
    raise NotImplementedError("Implemented in Phase 1")
