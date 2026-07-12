import io
import uvicorn
from fastapi import FastAPI, File, Form, Header, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from faster_whisper import WhisperModel

model = WhisperModel("large-v3", device="cpu", compute_type="float16")

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "OPTIONS"],
    allow_headers=["*"],
)

@app.post("/stt/")
async def transcribe(
    file: UploadFile = File(...),
    language: str = Form(""),
    language_header: str = Header("", alias="X-Veksha-STT-Language"),
):
    data = await file.read()
    language_hint = (language or language_header).strip().lower().split("-", 1)[0].split("_", 1)[0]
    segments, _ = model.transcribe(io.BytesIO(data), language=language_hint or None)
    text = " ".join(s.text.strip() for s in segments)
    return {"text": text}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8765)
