"""同一批片段跑线上现用的 v1 default（Tokyo）做基线：同样的延迟定义（v1 用 result_end_time）和 CER。结果写 results_v1.json。"""
import asyncio
import json
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent / "lib"))
from google.cloud import speech_v1 as speech  # noqa: E402

from bench import CHUNK, HERE, cer, norm, norm_nofill, pct  # noqa: E402

CONCURRENCY = 4


async def run_one(clip, sem):
    async with sem:
        audio = clip.read_bytes()
        client = speech.SpeechAsyncClient()
        cfg = speech.RecognitionConfig(encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16, sample_rate_hertz=16000,
                                       language_code="ja-JP", enable_automatic_punctuation=True)
        scfg = speech.StreamingRecognitionConfig(config=cfg, interim_results=True)
        t0 = None
        events = []

        async def reqs():
            nonlocal t0
            yield speech.StreamingRecognizeRequest(streaming_config=scfg)
            t0 = time.monotonic()
            for i in range(0, len(audio), CHUNK):
                yield speech.StreamingRecognizeRequest(audio_content=audio[i:i + CHUNK])
                await asyncio.sleep(max(0.0, t0 + (i + CHUNK) / 32000 - time.monotonic()))

        err = None
        try:
            resp = await client.streaming_recognize(requests=reqs())
            async for r in resp:
                now = time.monotonic()
                for res in r.results:
                    if not res.alternatives:
                        continue
                    txt = res.alternatives[0].transcript.strip()
                    if not txt:
                        continue
                    eo = res.result_end_time
                    end_off = eo.total_seconds() if hasattr(eo, "total_seconds") else None
                    events.append({"t": now - t0, "final": bool(res.is_final), "end": end_off, "text": txt})
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:200]}"
        dur = len(audio) / 32000
        finals = [e for e in events if e["final"]]
        interims = [e for e in events if not e["final"]]
        lag = lambda e: (e["t"] - e["end"]) if e["end"] is not None else None  # noqa: E731
        all_lags = [x for x in (lag(e) for e in events) if x is not None]
        fin_lags = [x for x in (lag(e) for e in finals) if x is not None]
        ref = (HERE / "ref" / (clip.stem + ".txt")).read_text(encoding="utf-8")
        hyp = "".join(e["text"] for e in finals)
        out = {"clip": clip.stem, "mode": "v1-default", "duration": dur, "error": err,
               "n_interim": len(interims), "n_final": len(finals),
               "first_interim_t": interims[0]["t"] if interims else None,
               "first_interim_lag": lag(interims[0]) if interims else None,
               "subtitle_p50": pct(all_lags, 0.5), "subtitle_p90": pct(all_lags, 0.9),
               "final_p50": pct(fin_lags, 0.5), "final_p90": pct(fin_lags, 0.9),
               "cer": cer(norm(hyp), norm(ref)), "cer_nofill": cer(norm_nofill(hyp), norm_nofill(ref)),
               "events": events, "hyp": hyp}
        print(f"{clip.stem:20} v1 finals={len(finals):3} interims={len(interims):4} sub p50={out['subtitle_p50'] and round(out['subtitle_p50'],2)} "
              f"final p50={out['final_p50'] and round(out['final_p50'],2)} CER={round(out['cer'],3)} {err or ''}", flush=True)
        return out


async def main():
    clips = sorted((HERE / "clips").glob("*.pcm"))
    sem = asyncio.Semaphore(CONCURRENCY)
    results = await asyncio.gather(*[run_one(c, sem) for c in clips])
    (HERE / "results_v1.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved")


asyncio.run(main())
