#!/usr/bin/env bash
# Owner-only actions for the YCT project, run on YOUR Mac.
# Private keys and the HF token never leave this machine except: the HF token goes to
# AWS SSM Parameter Store (SecureString, encrypted). Only *public* keys are committed.
#
#   ./scripts/owner_mac.sh setup            # one-time: keys + HF token + pod permission + signed commit
#   ./scripts/owner_mac.sh spotcheck [n]    # P1 gate: decrypt sealed labels locally, show n random rows to verify
#   ./scripts/owner_mac.sh budget <usd>     # change GPU budget (signed commit)
#   ./scripts/owner_mac.sh approve "<text>" # signed DECISIONS.md entry (lift veto, approve deviation, etc.)
#   ./scripts/owner_mac.sh unblind          # P6: issue UNBLIND_TOKEN (signed) — only after unanimous GO
#
# Env overrides: AWS_PROFILE (default: default), AWS_REGION (eu-central-1), YCT_DIR (~/yct).
set -euo pipefail

REPO_URL="https://github.com/ArioMoniri/yct.git"
BRANCH="claude/yc-videos-agent-system-dirk8p"
YCT_DIR="${YCT_DIR:-$HOME/yct}"
REGION="${AWS_REGION:-eu-central-1}"
PARAM="/yct/hf_token"
INSTANCE_PROFILE="t3code-gpu-ssm-profile"
AGE_KEY="$HOME/.config/yct/owner.age.key"
SIGN_KEY="$HOME/.ssh/yct_signing"

say()  { printf "\n\033[1;34m==> %s\033[0m\n" "$*"; }
die()  { printf "\033[1;31mERROR: %s\033[0m\n" "$*" >&2; exit 1; }

need_tools() {
  command -v brew >/dev/null || die "Homebrew missing: https://brew.sh"
  for t in git age awscli jq; do
    bin="$t"; [ "$t" = awscli ] && bin=aws
    command -v "$bin" >/dev/null || { say "Installing $t"; brew install "$t"; }
  done
  aws sts get-caller-identity --region "$REGION" >/dev/null 2>&1 \
    || die "AWS CLI not logged in (run 'aws configure' or 'aws sso login', or set AWS_PROFILE)"
}

repo() {
  if [ ! -d "$YCT_DIR/.git" ]; then git clone -q -b "$BRANCH" "$REPO_URL" "$YCT_DIR"; fi
  cd "$YCT_DIR"
  git fetch -q origin "$BRANCH" && git checkout -q "$BRANCH" && git pull -q --ff-only origin "$BRANCH"
  # Sign every commit made in this clone with the owner key.
  git config gpg.format ssh
  git config user.signingkey "$SIGN_KEY.pub"
  git config commit.gpgsign true
  git config gpg.ssh.allowedSignersFile "$YCT_DIR/docs/allowed_signers"
}

push() { git push -q origin "$BRANCH" && say "Pushed signed commit $(git rev-parse --short HEAD)"; }

setup() {
  need_tools

  say "1/5 age key (decrypts sealed outcome labels; BACK IT UP, e.g. in your password manager)"
  mkdir -p "$(dirname "$AGE_KEY")"; chmod 700 "$(dirname "$AGE_KEY")"
  [ -f "$AGE_KEY" ] || age-keygen -o "$AGE_KEY" 2>/dev/null
  chmod 600 "$AGE_KEY"
  AGE_PUB=$(age-keygen -y "$AGE_KEY")

  say "2/5 SSH signing key (proves human-only actions came from you)"
  [ -f "$SIGN_KEY" ] || ssh-keygen -q -t ed25519 -C yct-owner -N "" -f "$SIGN_KEY"

  say "3/5 Hugging Face token"
  echo "Before continuing:"
  echo "  a) open https://huggingface.co/meta-llama/Llama-3.2-3B and accept the licence (approval can take hours)"
  echo "  b) create a FINE-GRAINED token at https://huggingface.co/settings/tokens with only:"
  echo "     'Read access to contents of all public gated repos you can access'"
  read -r -s -p "Paste HF token (hidden): " HF_TOKEN; echo
  [ -n "$HF_TOKEN" ] || die "empty token"
  who=$(curl -fsS -H "Authorization: Bearer $HF_TOKEN" https://huggingface.co/api/whoami-v2 | jq -r .name) \
    || die "token rejected by Hugging Face"
  echo "Token OK for HF user: $who"
  code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $HF_TOKEN" \
         https://huggingface.co/meta-llama/Llama-3.2-3B/resolve/main/config.json)
  if [ "$code" = 200 ]; then echo "Llama-3.2-3B access: GRANTED"
  else echo "Llama-3.2-3B access: NOT YET (HTTP $code). Token is stored anyway; GPU runs wait until Meta approves."; fi
  tmp=$(mktemp); chmod 600 "$tmp"
  jq -n --arg n "$PARAM" --arg v "$HF_TOKEN" \
     '{Name:$n,Value:$v,Type:"SecureString",Overwrite:true,Description:"YCT HF read token (owner)"}' > "$tmp"
  aws ssm put-parameter --region "$REGION" --cli-input-json "file://$tmp" >/dev/null
  rm -f "$tmp"; unset HF_TOKEN
  echo "Stored in SSM Parameter Store: $PARAM ($REGION, SecureString)"

  say "4/5 Allow the pod role to read only that parameter"
  ROLE=$(aws iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE" \
         --query 'InstanceProfile.Roles[0].RoleName' --output text)
  ACCT=$(aws sts get-caller-identity --query Account --output text)
  aws iam put-role-policy --role-name "$ROLE" --policy-name yct-read-hf-token --policy-document "$(jq -n \
    --arg p "arn:aws:ssm:$REGION:$ACCT:parameter$PARAM" --arg r "$REGION" '{
      Version:"2012-10-17",
      Statement:[
        {Effect:"Allow",Action:["ssm:GetParameter"],Resource:$p},
        {Effect:"Allow",Action:["kms:Decrypt"],Resource:"*",
         Condition:{StringEquals:{"kms:ViaService":("ssm."+$r+".amazonaws.com")}}}]}')"
  echo "Role $ROLE may read $PARAM"

  say "5/5 Commit public keys + re-sign DATA_DECISION and budget (signed commit)"
  repo
  echo "$AGE_PUB" > docs/owner_age.pub
  cp "$SIGN_KEY.pub" docs/owner_signing_key.pub
  echo "yct-owner $(cat "$SIGN_KEY.pub")" > docs/allowed_signers
  printf '\n**Owner re-signature:** this file and infra/BUDGET_USD (=%s) confirmed by SSH-signed commit on %s.\n' \
    "$(cat infra/BUDGET_USD)" "$(date -u +%F)" >> DATA_DECISION.md
  git add docs/owner_age.pub docs/owner_signing_key.pub docs/allowed_signers DATA_DECISION.md
  git commit -q -S -m "Owner: public keys (age, SSH signing); re-sign DATA_DECISION and budget"
  git verify-commit HEAD >/dev/null 2>&1 && echo "Signature verified locally"
  push
  say "Done. Keep $AGE_KEY and $SIGN_KEY private and backed up."
}

spotcheck() {
  need_tools; repo
  n="${1:-10}"
  [ -f data/sealed/labels.csv.age ] || die "no sealed labels yet (Phase 1 not finished)"
  age -d -i "$AGE_KEY" data/sealed/labels.csv.age \
    | python3 -c "import csv,random,sys; r=list(csv.DictReader(sys.stdin)); random.seed(); [print(x) for x in random.sample(r,min($n,len(r)))]"
  echo; echo "Open each evidence_url and confirm the outcome. Then run:"
  echo "  $0 approve \"P1 spot-check: $n rows verified, <k> errors: <details>\""
}

budget() {
  [ -n "${1:-}" ] || die "usage: budget <usd>"
  need_tools; repo
  echo "$1" > infra/BUDGET_USD
  printf '\n- %s | OWNER | GPU budget set to USD %s (signed commit)\n' "$(date -u +%F)" "$1" >> DECISIONS.md
  git add infra/BUDGET_USD DECISIONS.md && git commit -q -S -m "Owner: GPU budget USD $1" && push
}

approve() {
  [ -n "${1:-}" ] || die "usage: approve \"<decision text>\""
  need_tools; repo
  printf '\n- %s | OWNER | %s (signed commit)\n' "$(date -u +%F)" "$1" >> DECISIONS.md
  git add DECISIONS.md && git commit -q -S -m "Owner decision: ${1:0:60}" && push
}

unblind() {
  need_tools; repo
  git tag -l prereg-lock | grep -q . || die "no prereg-lock tag: Phase 6 not reached"
  echo "Prereg locked at $(git rev-list -n1 prereg-lock). Confirm the P6 gate shows unanimous GO + Watchdog PASS."
  read -r -p "Type UNBLIND to proceed: " ok; [ "$ok" = UNBLIND ] || die "aborted"
  # Hand the analysis the true labels: re-encrypt is not needed; the pipeline decrypts in-memory on
  # the pod only after seeing this signed token. The token binds to the prereg commit.
  printf 'prereg=%s\nissued=%s\n' "$(git rev-list -n1 prereg-lock)" "$(date -u +%FT%TZ)" > UNBLIND_TOKEN
  git add UNBLIND_TOKEN && git commit -q -S -m "Owner: UNBLIND_TOKEN" && push
  echo "Next: run '$0 release-labels' to give the pod the label key for this run."
}

release_labels() {
  # Puts the age private key into SSM as SecureString so the pod can decrypt labels after unblinding.
  need_tools; repo
  [ -f UNBLIND_TOKEN ] || die "UNBLIND_TOKEN not issued"
  tmp=$(mktemp); chmod 600 "$tmp"
  jq -n --arg v "$(cat "$AGE_KEY")" '{Name:"/yct/age_key",Value:$v,Type:"SecureString",Overwrite:true}' > "$tmp"
  aws ssm put-parameter --region "$REGION" --cli-input-json "file://$tmp" >/dev/null; rm -f "$tmp"
  ROLE=$(aws iam get-instance-profile --instance-profile-name "$INSTANCE_PROFILE" \
         --query 'InstanceProfile.Roles[0].RoleName' --output text)
  ACCT=$(aws sts get-caller-identity --query Account --output text)
  aws iam put-role-policy --role-name "$ROLE" --policy-name yct-read-age-key --policy-document "$(jq -n \
    --arg p "arn:aws:ssm:$REGION:$ACCT:parameter/yct/age_key" '{Version:"2012-10-17",
     Statement:[{Effect:"Allow",Action:["ssm:GetParameter"],Resource:$p}]}')"
  say "Label key released to the pod. Delete later with: aws ssm delete-parameter --name /yct/age_key"
}

case "${1:-}" in
  setup) setup ;;
  spotcheck) shift; spotcheck "${1:-10}" ;;
  budget) shift; budget "${1:-}" ;;
  approve) shift; approve "${1:-}" ;;
  unblind) unblind ;;
  release-labels) release_labels ;;
  *) sed -n '2,13p' "$0"; exit 1 ;;
esac
