"""汇总 results.json：按模式合并所有片段的延迟分布、切分数、CER（用 ref/ 重算，和 bench 跑的时序无关）。"""
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent / "lib"))
from bench import cer, norm, norm_nofill, pct  # noqa: E402

HERE = pathlib.Path(__file__).parent
results = json.loads((HERE / "results.json").read_text(encoding="utf-8"))
if (HERE / "results_v1.json").exists():
    results += json.loads((HERE / "results_v1.json").read_text(encoding="utf-8"))
modes = []
for r in results:
    if r["mode"] not in modes:
        modes.append(r["mode"])


def fmt(x, nd=2):
    return "-" if x is None else f"{x:.{nd}f}"


agg = {}
for m in modes:
    rs = [r for r in results if r["mode"] == m and not r["error"]]
    all_lags, fin_lags, first_t, first_lag = [], [], [], []
    n_fin = n_int = 0
    dist = dist_nf = reflen = reflen_nf = 0
    dur = 0.0
    hyplen_nf = 0
    for r in rs:
        ev = r["events"]
        lag = lambda e: (e["t"] - e["end"]) if e["end"] is not None else None  # noqa: E731
        all_lags += [x for x in (lag(e) for e in ev) if x is not None]
        fin = [e for e in ev if e["final"]]
        itm = [e for e in ev if not e["final"]]
        fin_lags += [x for x in (lag(e) for e in fin) if x is not None]
        if itm:
            first_t.append(itm[0]["t"])
            if lag(itm[0]) is not None:
                first_lag.append(lag(itm[0]))
        n_fin += len(fin); n_int += len(itm); dur += r["duration"]
        ref = (HERE / "ref" / (r["clip"] + ".txt")).read_text(encoding="utf-8")
        hyp = "".join(e["text"] for e in fin)
        from rapidfuzz.distance import Levenshtein
        dist += Levenshtein.distance(norm(hyp), norm(ref)); reflen += len(norm(ref))
        dist_nf += Levenshtein.distance(norm_nofill(hyp), norm_nofill(ref)); reflen_nf += len(norm_nofill(ref)); hyplen_nf += len(norm_nofill(hyp))
    agg[m] = {
        "clips": len(rs), "errors": sum(1 for r in results if r["mode"] == m and r["error"]),
        "first_interim_t_mean": sum(first_t) / len(first_t) if first_t else None,
        "first_interim_t_p50": pct(first_t, 0.5),
        "first_interim_lag_p50": pct(first_lag, 0.5),
        "n_updates": len(all_lags), "sub_p50": pct(all_lags, 0.5), "sub_p90": pct(all_lags, 0.9),
        "n_final": n_fin, "n_interim": n_int,
        "final_p50": pct(fin_lags, 0.5), "final_p90": pct(fin_lags, 0.9), "final_max": max(fin_lags) if fin_lags else None,
        "seg_per_min": n_fin / (dur / 60) if dur else None, "seg_len_s": dur / n_fin if n_fin else None,
        "cer": dist / reflen if reflen else None, "coverage": hyplen_nf / reflen_nf if reflen_nf else None, "cer_nofill": dist_nf / reflen_nf if reflen_nf else None,
    }

print("| 指标 | " + " | ".join(modes) + " |")
print("|---|" + "---|" * len(modes))
rows = [
    ("片段数（出错）", lambda a: f"{a['clips']}（{a['errors']}）"),
    ("首个 interim 出现时刻 均值 / P50（秒）", lambda a: f"{fmt(a['first_interim_t_mean'],1)} / {fmt(a['first_interim_t_p50'],1)}"),
    ("首个 interim 的延迟 P50（秒）", lambda a: fmt(a['first_interim_lag_p50'])),
    ("字幕延迟 P50 / P90（秒，interim+final）", lambda a: f"{fmt(a['sub_p50'])} / {fmt(a['sub_p90'])}"),
    ("final 延迟 P50 / P90 / 最大（秒）", lambda a: f"{fmt(a['final_p50'])} / {fmt(a['final_p90'])} / {fmt(a['final_max'])}"),
    ("interim 条数（16 分钟合计）", lambda a: str(a['n_interim'])),
    ("final 条数 = 切分次数（16 分钟合计）", lambda a: str(a['n_final'])),
    ("每分钟切分次数 / 平均片段长（秒）", lambda a: f"{fmt(a['seg_per_min'],1)} / {fmt(a['seg_len_s'],1)}"),
    ("字数覆盖率（去填充词后 识别字数 / 参照字数）", lambda a: fmt(a["coverage"])),
    ("CER（去标点空白）", lambda a: fmt(a['cer'] * 100 if a['cer'] is not None else None, 1) + "%"),
    ("CER（再去填充词）", lambda a: fmt(a['cer_nofill'] * 100 if a['cer_nofill'] is not None else None, 1) + "%"),
]
for label, f in rows:
    print(f"| {label} | " + " | ".join(f(agg[m]) for m in modes) + " |")

print("\n按片段：")
print("| 片段 | 模式 | interim | final | 字幕P50 | finalP50 | CER |")
print("|---|---|---|---|---|---|---|")
for r in results:
    ref = (HERE / "ref" / (r["clip"] + ".txt")).read_text(encoding="utf-8")
    hyp = "".join(e["text"] for e in r["events"] if e["final"])
    c = cer(norm(hyp), norm(ref))
    print(f"| {r['clip']} | {r['mode']} | {r['n_interim']} | {r['n_final']} | {fmt(r['subtitle_p50'])} | {fmt(r['final_p50'])} | {c*100:.1f}% |"
          + (f" {r['error']}" if r["error"] else ""))
