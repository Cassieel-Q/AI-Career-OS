from fastapi import FastAPI

app = FastAPI(title="AI Career OS API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    """Return the service liveness status."""
    return {"status": "ok"}
