"""chirp_3 流式：endpointing_sensitivity STANDARD vs SHORT（可加 SUPERSHORT），同一批日语片段。

每个片段按实时速率喂音频（和前端一帧 ~85ms 一致）。对每条结果记录：
  arrival  = 到达时刻（相对第一帧音频送出）
  end_off  = result_end_offset（该结果覆盖到的音频时刻，服务端给）
  lag      = arrival - end_off   ← 字幕延迟：这段话说完到它出现在屏幕上隔了多久
指标：
  first_interim      首个 interim 的到达时刻 和 它的 lag
  subtitle P50/P90   所有屏幕更新（interim + final）的 lag 分位数
  final P50/P90      final 的 lag 分位数
  segments           final 条数（切分次数）
  CER                finals 拼接 vs 参照（去标点空白后的字符编辑距离 / 参照长度）；另给去填充词版本
结果写 results.json，汇总由 report.py 生成。
"""
import asyncio
import json
import pathlib
import re
import sys
import time
import unicodedata

sys.path.insert(0, str(pathlib.Path(__file__).parent / "lib"))
from rapidfuzz.distance import Levenshtein  # noqa: E402
from google.api_core.client_options import ClientOptions  # noqa: E402
from google.cloud.speech_v2 import SpeechAsyncClient  # noqa: E402
from google.cloud.speech_v2.types import cloud_speech as cs  # noqa: E402

HERE = pathlib.Path(__file__).parent
CHUNK = 2730
REGION, MODEL, PROJECT = "us", "chirp_3", "lectrace"
MODES = sys.argv[1].split(",") if len(sys.argv) > 1 else ["STANDARD", "SHORT"]
CONCURRENCY = 4

PUNCT = re.compile(r"[\s、。，．,.!?！？・「」『』（）()\[\]【】:：;；…ー〜~\-–—\"'“”‘’]")
FILLERS = re.compile(r"(えっと|えーと|えー|えっ|ええ|あの|あのー|その|まあ|ま、|え、|ま|え|うん|はい|ね)")


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return PUNCT.sub("", s)


def norm_nofill(s: str) -> str:
    # 先去标点再去填充词：填充词正则里的单字（え/ま/ね）只在被标点隔开时才算，所以先在原文上处理
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"(?<![ぁ-ん一-龥])(えっと|えーと|えー|あのー|あの|まあ)(?![ぁ-ん一-龥])", "", s)
    s = re.sub(r"[、，,]\s*(え|ま|ね|うん|はい)\s*[、，,]", "、", s)
    s = re.sub(r"(^|[。、，,.])\s*(え|ま|うん|はい)\s*[、，,]", r"\1", s)
    return PUNCT.sub("", s)


def cer(hyp: str, ref: str) -> float:
    return Levenshtein.distance(hyp, ref) / max(1, len(ref))


def pct(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


async def run_one(clip: pathlib.Path, mode: str, sem: asyncio.Semaphore) -> dict:
    async with sem:
        audio = clip.read_bytes()
        client = SpeechAsyncClient(client_options=ClientOptions(api_endpoint=f"{REGION}-speech.googleapis.com"))
        cfg = cs.RecognitionConfig(
            explicit_decoding_config=cs.ExplicitDecodingConfig(
                encoding=cs.ExplicitDecodingConfig.AudioEncoding.LINEAR16, sample_rate_hertz=16000, audio_channel_count=1),
            language_codes=["ja-JP"], model=MODEL,
            features=cs.RecognitionFeatures(enable_automatic_punctuation=True),
        )
        scfg = cs.StreamingRecognitionConfig(
            config=cfg,
            streaming_features=cs.StreamingRecognitionFeatures(
                interim_results=True,
                endpointing_sensitivity=getattr(cs.StreamingRecognitionFeatures.EndpointingSensitivity, f"ENDPOINTING_SENSITIVITY_{mode}"),
            ),
        )
        t0 = None
        events = []

        async def reqs():
            nonlocal t0
            yield cs.StreamingRecognizeRequest(recognizer=f"projects/{PROJECT}/locations/{REGION}/recognizers/_", streaming_config=scfg)
            t0 = time.monotonic()
            for i in range(0, len(audio), CHUNK):
                yield cs.StreamingRecognizeRequest(audio=audio[i:i + CHUNK])
                # 按实时速率：第 k 帧应在 k*CHUNK/32000 秒送出
                target = t0 + (i + CHUNK) / 32000
                await asyncio.sleep(max(0.0, target - time.monotonic()))

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
                    eo = res.result_end_offset
                    end_off = eo.total_seconds() if hasattr(eo, "total_seconds") else float(eo.seconds + eo.nanos / 1e9) if eo else None
                    events.append({"t": now - t0, "final": bool(res.is_final), "end": end_off, "text": txt})
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {str(e)[:200]}"
        dur = len(audio) / 32000
        finals = [e for e in events if e["final"]]
        interims = [e for e in events if not e["final"]]
        lag = lambda e: (e["t"] - e["end"]) if e["end"] is not None else None  # noqa: E731
        all_lags = [x for x in (lag(e) for e in events) if x is not None]
        fin_lags = [x for x in (lag(e) for e in finals) if x is not None]
        ref_path = HERE / "ref" / (clip.stem + ".txt")
        ref = ref_path.read_text(encoding="utf-8") if ref_path.exists() else ""
        hyp = "".join(e["text"] for e in finals)
        out = {
            "clip": clip.stem, "mode": mode, "duration": dur, "error": err,
            "n_interim": len(interims), "n_final": len(finals),
            "first_interim_t": interims[0]["t"] if interims else None,
            "first_interim_lag": lag(interims[0]) if interims else None,
            "first_final_t": finals[0]["t"] if finals else None,
            "subtitle_p50": pct(all_lags, 0.5), "subtitle_p90": pct(all_lags, 0.9),
            "final_p50": pct(fin_lags, 0.5), "final_p90": pct(fin_lags, 0.9), "final_max": max(fin_lags) if fin_lags else None,
            "seg_len_mean_s": (dur / len(finals)) if finals else None,
            "hyp_chars": len(norm(hyp)), "ref_chars": len(norm(ref)),
            "cer": cer(norm(hyp), norm(ref)) if ref else None,
            "cer_nofill": cer(norm_nofill(hyp), norm_nofill(ref)) if ref else None,
            "events": events, "hyp": hyp,
        }
        print(f"{clip.stem:20} {mode:8} finals={len(finals):3} interims={len(interims):3} "
              f"sub p50={out['subtitle_p50'] and round(out['subtitle_p50'],2)} final p50={out['final_p50'] and round(out['final_p50'],2)} "
              f"CER={out['cer'] and round(out['cer'],3)} {err or ''}", flush=True)
        return out


async def main():
    clips = sorted((HERE / "clips").glob("*.pcm"))
    sem = asyncio.Semaphore(CONCURRENCY)
    tasks = [run_one(c, m, sem) for m in MODES for c in clips]
    results = await asyncio.gather(*tasks)
    (HERE / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", len(results), "runs")


if __name__ == "__main__":
    asyncio.run(main())
