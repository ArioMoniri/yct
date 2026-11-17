#!/usr/bin/env bash
# OWNER ONLY — run on your Mac (AWS CLI logged in). Downloads the wave-1 YouTube videos from your home
# connection (the EC2 pod gets YouTube bot-checks, BUG-025), keeps them in DEST, and uploads them to a
# private encrypted S3 bucket the EC2 pod can read. No repo clone; no brew. Needs: aws, curl, python3.
#   DEST           local folder (default below)
#   BUCKET         S3 bucket (default yct-research-<account id>, eu-central-1, private, SSE-S3)
#   FORMAT         yt-dlp format selector (default: SDR-first, see ENH-006 below; the previous selector
#                  "b[ext=mp4][height>=360]/b[ext=mp4]/b" is the tail of the default chain, so behaviour is
#                  unchanged wherever an SDR progressive mp4 exists, which is every progressive YouTube mp4)
# Files are named <video_id>.<ext> only — no titles are printed or stored (blinding).
set -euo pipefail
DEST="${DEST:-/Volumes/X10 Pro/Macbook/yt}"
REF="${REF:-claude/yc-videos-agent-system-dirk8p}"
# ENH-006 (Neuro G-D032 A2): prefer SDR. [dynamic_range=?SDR] keeps SDR (or unknown-range) formats;
# [vcodec!*=vp09.02] drops VP9 profile 2 (the YouTube HDR codec). Fallbacks: old selector. Any HDR file
# that still arrives is detected (ffprobe color_transfer PQ/HLG) and tone-mapped + flagged in P2.
SDR_FORMAT='b[ext=mp4][height>=360][dynamic_range=?SDR][vcodec!*=vp09.02]/b[ext=mp4][dynamic_range=?SDR][vcodec!*=vp09.02]'
FORMAT="${FORMAT:-$SDR_FORMAT/b[ext=mp4][height>=360]/b[ext=mp4]/b}"
export AWS_DEFAULT_REGION=eu-central-1
for c in aws curl python3; do command -v "$c" >/dev/null || { echo "$c not found"; exit 1; }; done
ACCT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="${BUCKET:-yct-research-$ACCT}"
ROLE=$(aws iam get-instance-profile --instance-profile-name t3code-gpu-ssm-profile \
       --query 'InstanceProfile.Roles[0].RoleName' --output text)
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
mkdir -p "$DEST/raw"
echo "== 1. yt-dlp (standalone macOS binary, temp only) =="
curl -fsSL https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp_macos -o "$TMP/yt-dlp"
chmod +x "$TMP/yt-dlp"; xattr -d com.apple.quarantine "$TMP/yt-dlp" 2>/dev/null || true
echo "  yt-dlp $("$TMP/yt-dlp" --version)"

echo "== 2. wave-1 YouTube list from the public manifest (ids + urls only) =="
curl -fsSL "https://raw.githubusercontent.com/ArioMoniri/yct/$REF/data/manifest.csv" -o "$TMP/manifest.csv"
python3 - "$TMP/manifest.csv" > "$TMP/list.tsv" <<'PY'
import csv, sys
for r in csv.DictReader(open(sys.argv[1], newline="")):
    if r["in_primary"] == "True" and r["platform"].strip().lower() == "youtube" and not r["url"].startswith("sealed:"):
        print(f'{r["video_id"]}\t{r["url"]}')
PY
N=$(wc -l < "$TMP/list.tsv" | tr -d ' '); echo "  $N YouTube videos"

echo "== 3. download (polite pacing; stops on bot-check; skips files already present) =="
ok=0; fail=0
while IFS=$'\t' read -r vid url; do
  if ls "$DEST/raw/$vid".* >/dev/null 2>&1; then ok=$((ok+1)); continue; fi
  # progressive mp4 (no ffmpeg needed); >=360p short side satisfies the >=292 px requirement
  if "$TMP/yt-dlp" -q --no-warnings --no-playlist --sleep-requests 2 --sleep-interval 5 --max-sleep-interval 15 \
       -f "$FORMAT" -o "$DEST/raw/$vid.%(ext)s" "$url" 2> "$TMP/err.txt"; then
    ok=$((ok+1)); printf "  %s ok (%d/%s)\n" "$vid" "$ok" "$N"
  elif "$TMP/yt-dlp" -q --no-warnings --no-playlist --sleep-requests 2 --sleep-interval 5 \
         -f "bv*[height<=720][ext=mp4]/bv*[height<=720]" -o "$DEST/raw/$vid.video.%(ext)s" "$url" 2>> "$TMP/err.txt" \
       && "$TMP/yt-dlp" -q --no-warnings --no-playlist --sleep-requests 2 \
         -f "ba[ext=m4a]/ba" -o "$DEST/raw/$vid.audio.%(ext)s" "$url" 2>> "$TMP/err.txt"; then
    # no single-file format: separate streams; the pod merges them with ffmpeg (no ffmpeg needed here)
    ok=$((ok+1)); printf "  %s ok, split streams (%d/%s)\n" "$vid" "$ok" "$N"
  else
    { echo "== $vid"; sed -E 's/\[youtube\][^:]*: //' "$TMP/err.txt" | tail -3; } >> "$DEST/failed_detail.txt"
    fail=$((fail+1)); cls=$(grep -oiE "not a bot|429|private|unavailable|removed|copyright|age|format" "$TMP/err.txt" | head -1 || true)
    printf "  %s FAILED (%s)\n" "$vid" "${cls:-other}"; echo -e "$vid\t${cls:-other}" >> "$DEST/failed.tsv"
    if echo "$cls" | grep -qiE "not a bot|429"; then echo "  rate-limited/bot-check: stopping (rerun later resumes)"; break; fi
  fi
done < "$TMP/list.tsv"
echo "  downloaded/present: $ok, failed: $fail  (failure details, local only: $DEST/failed_detail.txt)"

echo "== 3b. sealed-URL rows (decrypted locally with your key; URL never printed) =="
for f in sealed_p1c_urls.tar.age sealed_p1c_urls.tar.age.sha256; do
  curl -fsSL "https://raw.githubusercontent.com/ArioMoniri/yct/$REF/data/sealed/$f" -o "$TMP/$f"
done
( cd "$TMP" && shasum -a 256 -c sealed_p1c_urls.tar.age.sha256 >/dev/null ) || { echo "  sealed checksum mismatch"; exit 1; }
case "$(uname -m)" in arm64) A=darwin-arm64;; *) A=darwin-amd64;; esac
curl -fsSL "https://github.com/FiloSottile/age/releases/download/v1.2.1/age-v1.2.1-$A.tar.gz" | tar xz -C "$TMP"
aws ssm get-parameter --name /yct/owner/age_key --with-decryption --query Parameter.Value --output text > "$TMP/k"
mkdir -p "$TMP/su"; "$TMP/age/age" -d -i "$TMP/k" "$TMP/sealed_p1c_urls.tar.age" | tar x -C "$TMP/su"; rm -f "$TMP/k"
python3 - "$TMP/su" "$TMP/manifest.csv" > "$TMP/sealed.tsv" <<'PY'
import csv, glob, sys
prim = {r["video_id"] for r in csv.DictReader(open(sys.argv[2], newline="")) if r["in_primary"] == "True"}
for p in glob.glob(sys.argv[1] + "/**/*.csv", recursive=True):
    for r in csv.DictReader(open(p, newline="", encoding="utf-8")):
        if r.get("video_id") in prim and r.get("url"):
            print(f'{r["video_id"]}\t{r["url"]}')
PY
while IFS=$'\t' read -r vid url; do
  if ls "$DEST/raw/$vid".* >/dev/null 2>&1; then echo "  $vid present"; continue; fi
  if curl -fsSL --retry 3 "$url" -o "$DEST/raw/$vid.mp4"; then echo "  $vid ok (sealed url)"; else echo "  $vid FAILED (sealed url)"; fi
done < "$TMP/sealed.tsv"

echo "== 4. checksums =="
( cd "$DEST/raw" && shasum -a 256 yct_* > ../SHA256SUMS ) && echo "  $(wc -l < "$DEST/SHA256SUMS" | tr -d ' ') files hashed"

echo "== 5. private encrypted S3 bucket + upload =="
if ! aws s3api head-bucket --bucket "$BUCKET" 2>/dev/null; then
  aws s3api create-bucket --bucket "$BUCKET" --create-bucket-configuration LocationConstraint=eu-central-1 >/dev/null
  aws s3api put-public-access-block --bucket "$BUCKET" --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
  aws s3api put-bucket-encryption --bucket "$BUCKET" --server-side-encryption-configuration \
    '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]}'
  echo "  created s3://$BUCKET (private, SSE-S3)"
fi
aws s3 sync "$DEST/raw" "s3://$BUCKET/wave1/raw/" --only-show-errors
aws s3 cp "$DEST/SHA256SUMS" "s3://$BUCKET/wave1/SHA256SUMS" --only-show-errors
echo "  uploaded to s3://$BUCKET/wave1/raw/"

echo "== 6. pod + Claude access to this bucket only =="
POL=$(printf '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":["s3:ListBucket"],"Resource":"arn:aws:s3:::%s"},{"Effect":"Allow","Action":["s3:GetObject","s3:PutObject"],"Resource":"arn:aws:s3:::%s/*"}]}' "$BUCKET" "$BUCKET")
aws iam put-role-policy --role-name "$ROLE" --policy-name yct-s3-research --policy-document "$POL"
aws iam put-user-policy --user-name tribe-pod-manager --policy-name yct-s3-research --policy-document "$POL"
echo "DONE. Local copy kept in: $DEST   Tell Claude: downloads done (+ the ok/failed counts above)."
