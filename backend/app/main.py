from fastapi import FastAPI

app = FastAPI(title="FindAI API", version="0.1.0")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "FindAI API is running"}
