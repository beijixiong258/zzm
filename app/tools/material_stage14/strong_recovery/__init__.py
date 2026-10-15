"""Offline literal-line evidence proposals; no worker integration or GPU lifecycle."""
from .alignment import align_evidence
from .protocol import LoopbackLineClient, HTTPReply

__all__ = ["align_evidence", "LoopbackLineClient", "HTTPReply"]
