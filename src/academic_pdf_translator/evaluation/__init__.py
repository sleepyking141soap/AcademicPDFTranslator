"""Human annotation and benchmark support for real-paper evaluation."""

from .metrics import evaluate_workspace
from .storage import add_document, init_workspace, load_workspace

__all__ = ["add_document", "evaluate_workspace", "init_workspace", "load_workspace"]
