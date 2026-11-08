__all__ = ["CortexEngine", "ScopeManager"]


def __getattr__(name):
    # Hooks use privacy helpers without importing PyTorch/spaCy.
    if name == "CortexEngine":
        from cortex_claude.core.engine import CortexEngine
        return CortexEngine
    if name == "ScopeManager":
        from cortex_claude.core.scope_manager import ScopeManager
        return ScopeManager
    raise AttributeError(name)
