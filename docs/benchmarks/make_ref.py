"""参照转写：每段 PCM 包成 WAV，送 OpenAI gpt-4o-transcribe（离线、非流式、高精度）当 CER 的参照。
不是人工标注，只是独立的第三方高质量结果；结果存 ref/<clip>.txt。"""
import io
import os
import pathlib
import sys
import wave

import httpx
from dotenv import dotenv_values

HERE = pathlib.Path(__file__).parent
env = dotenv_values("/Users/huyang/Desktop/Coding/LecTrace/.env")
KEY = env["OPENAI_API_KEY"]
MODEL = sys.argv[1] if len(sys.argv) > 1 else "gpt-4o-transcribe"
(HERE / "ref").mkdir(exist_ok=True)

for pcm in sorted((HERE / "clips").glob("*.pcm")):
    out = HERE / "ref" / (pcm.stem + ".txt")
    if out.exists():
        print("skip", pcm.name); continue
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000); w.writeframes(pcm.read_bytes())
    r = httpx.post(
        "https://api.openai.com/v1/audio/transcriptions",
        headers={"Authorization": f"Bearer {KEY}"},
        files={"file": (pcm.stem + ".wav", buf.getvalue(), "audio/wav")},
        data={"model": MODEL, "language": "ja", "response_format": "json", "temperature": "0"},
        timeout=300,
    )
    r.raise_for_status()
    text = r.json()["text"]
    out.write_text(text, encoding="utf-8")
    print(f"{pcm.name}: {len(text)} chars  {text[:60]}")
