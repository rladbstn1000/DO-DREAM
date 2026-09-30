"""Opt-in, bounded Phase 5 providers. Importing this package performs no I/O."""
from .contract import (CallScope, EMBEDDING_MODEL, CHAT_MODEL, LIVE_SPEC,
                       ProviderError, ProviderMode, load_manifest)
from .budget import BudgetLedger

__all__ = ["CallScope", "EMBEDDING_MODEL", "CHAT_MODEL", "LIVE_SPEC", "ProviderError",
           "ProviderMode", "load_manifest", "BudgetLedger", "LiveOpenAI",
           "approved_material_ids", "authorize_scope"]


def __getattr__(name):
    if name in {"LiveOpenAI", "approved_material_ids", "authorize_scope"}:
        from . import openai
        return getattr(openai, name)
    raise AttributeError(name)
