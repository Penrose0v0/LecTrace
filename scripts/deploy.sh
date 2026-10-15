#!/usr/bin/env bash
# 部署到 Cloud Run：从 .env 生成环境变量文件（剔除本地专用项），整体替换线上变量后部署。
#
#   scripts/deploy.sh            生成 .cloudrun.env.yaml 并部署
#   scripts/deploy.sh --dry-run  只生成并列出会上线的变量名，不部署
#
# 用 --env-vars-file 而不是 --set-env-vars：值里有逗号/等号也安全，且线上多余的旧变量会被清掉。
set -euo pipefail
cd "$(dirname "$0")/.."

SERVICE=lectrace
REGION=asia-northeast1
OUT=.cloudrun.env.yaml

# 只在本地有意义的键，不上线
LOCAL_ONLY="AUTH_DEV_LOGIN RECORDINGS_DIR DEMO_DATA_DIR REPLAY_SPEED REPLAY_MAX_GAP_SEC FIRESTORE_EMULATOR_HOST GOOGLE_CLOUD_PROJECT"

python3 - "$OUT" $LOCAL_ONLY <<'EOF'
import sys, re, pathlib
out, skip = sys.argv[1], set(sys.argv[2:])
rows = []
for line in pathlib.Path(".env").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    k, v = line.split("=", 1)
    k, v = k.strip(), v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        v = v[1:-1]
    if k in skip or not v:
        continue
    rows.append((k, v))
required = {"GOOGLE_CLIENT_ID", "SESSION_SECRET", "STORE_BACKEND", "GCP_PROJECT"}
missing = required - {k for k, _ in rows}
if missing:
    sys.exit(f"缺少必填变量: {', '.join(sorted(missing))}")
if dict(rows).get("STORE_BACKEND") != "firestore":
    sys.exit("线上 STORE_BACKEND 必须是 firestore（内存后端重启即丢）")
yaml = "\n".join(f"{k}: {chr(34)}{v.replace(chr(92), chr(92)*2).replace(chr(34), chr(92)+chr(34))}{chr(34)}" for k, v in rows) + "\n"
pathlib.Path(out).write_text(yaml, encoding="utf-8")
print("将上线的变量：")
for k, v in rows:
    shown = v if not any(s in k for s in ("KEY", "SECRET")) else v[:4] + "…"
    print(f"  {k:28s} {shown}")
EOF

if [[ "${1:-}" == "--dry-run" ]]; then
  echo "(dry-run) 已生成 ${OUT}，未部署"
  exit 0
fi

gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --timeout=3600 \
  --env-vars-file "$OUT"

echo
gcloud run services describe "$SERVICE" --region "$REGION" --format="value(status.url)"
