from backend.app.api.dca import create_app


app = create_app()
app.title = "Hunter3 API"
app.version = "1.0.0"


@app.get("/health")
def health_check():
    return {"status": "ok"}
