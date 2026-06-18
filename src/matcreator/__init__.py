"""MatCreator — multi-agent framework for computational materials science."""

__all__ = ["app"]


def __getattr__(name: str):
    if name == "app":
        from .agent import app
        return app
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
