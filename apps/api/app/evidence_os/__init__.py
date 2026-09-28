"""Evidence OS — Phase-3 distilled resume ledger."""

__all__ = ["router"]


def __getattr__(name: str):
    if name == "router":
        from .routes import router

        return router
    raise AttributeError(name)
