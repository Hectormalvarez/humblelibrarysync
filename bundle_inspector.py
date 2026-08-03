"""
Backward-compatible shim for bundle_inspector.

All logic has been moved to humble_sync.services.evaluator.
This module re-exports everything so existing imports continue to work.
"""

from humble_sync.services.evaluator import *  # noqa: F401,F403