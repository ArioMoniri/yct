#!/usr/bin/env bash
# YCT owner setup. Runs on macOS (or AWS CloudShell) with the AWS CLI already logged in.
# No repo clone, no jq/brew. Fill in HF_TOKEN below, then: bash owner_setup.sh
HF_TOKEN="PASTE_YOUR_HF_TOKEN_HERE"
BUDGET_USD="200"

set -euo pipefail
export AWS_DEFAULT_REGION=eu-central-1
umask 077
[[ "$HF_TOKEN" == hf_* ]] || { echo "Set HF_TOKEN at the top of the script first."; exit 1; }
command -v aws >/dev/null || { echo "AWS CLI not found"; exit 1; }
ACCT=$(aws sts get-caller-identity --query Account --output text)
ME=$(aws sts get-caller-identity --query Arn --output text)
ROLE=$(aws iam get-instance-profile --instance-profile-name t3code-gpu-ssm-profile \
       --query 'InstanceProfile.Roles[0].RoleName' --output text)
P="arn:aws:ssm:eu-central-1:$ACCT:parameter"
TMP=$(mktemp -d); trap 'rm -rf "$TMP"' EXIT
echo "Owner: $ME | account $ACCT | pod role $ROLE"

put() {  # put <name> <type> <value>; value goes via a private temp file, never on the command line
  printf '{"Name":"%s","Type":"%s","Value":"%s","Overwrite":true}' "$1" "$2" "$3" > "$TMP/p.json"
  aws ssm put-parameter --cli-input-json "file://$TMP/p.json" >/dev/null; rm -f "$TMP/p.json"
  echo "  set $1"
}

echo "== 1. Hugging Face token =="
curl -fsS -H "Authorization: Bearer $HF_TOKEN" https://huggingface.co/api/whoami-v2 >/dev/null \
  || { echo "Hugging Face rejected the token"; exit 1; }
code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $HF_TOKEN" \
       https://huggingface.co/meta-llama/Llama-3.2-3B/resolve/main/config.json)
if [ "$code" = 200 ]; then echo "  Llama-3.2-3B access: GRANTED"
else echo "  Llama-3.2-3B access: PENDING (HTTP $code) - stored anyway; GPU runs wait for Meta's approval"; fi
put /yct/hf_token SecureString "$HF_TOKEN"

echo "== 2. Owner age key (seals outcome labels; private half never leaves SSM) =="
if aws ssm get-parameter --name /yct/owner/age_pub >/dev/null 2>&1; then
  echo "  age key already exists - kept"
else
  case "$(uname -s)-$(uname -m)" in
    Darwin-arm64) A=darwin-arm64 ;; Darwin-x86_64) A=darwin-amd64 ;;
    Linux-x86_64) A=linux-amd64 ;;  Linux-aarch64) A=linux-arm64 ;;
    *) echo "unsupported platform"; exit 1 ;;
  esac
  curl -fsSL "https://github.com/FiloSottile/age/releases/download/v1.2.1/age-v1.2.1-$A.tar.gz" | tar xz -C "$TMP"
  KEY=$("$TMP/age/age-keygen" 2>/dev/null | grep '^AGE-SECRET-KEY-')
  PUB=$(printf '%s\n' "$KEY" | "$TMP/age/age-keygen" -y)
  put /yct/owner/age_key SecureString "$KEY"; unset KEY
  put /yct/owner/age_pub String "$PUB"
fi

echo "== 3. Owner decisions =="
put /yct/owner/owner_arn String "$ME"
put /yct/owner/budget_usd String "$BUDGET_USD"
put /yct/owner/data_decision String "SIGNED $(date -u +%F) by $ME - DATA_DECISION.md v2.2 section 4 (repo commit 6c16d89)"

echo "== 4. Permissions =="
GUARD=$(cat <<EOF
{"Effect":"Allow","Action":["ssm:GetParameter","ssm:GetParameterHistory"],"Resource":[
  "$P/yct/owner/age_pub","$P/yct/owner/budget_usd","$P/yct/owner/data_decision",
  "$P/yct/owner/owner_arn","$P/yct/owner/unblind_token","$P/yct/owner/decisions"]},
{"Effect":"Deny","Action":["ssm:PutParameter","ssm:DeleteParameter","ssm:DeleteParameters",
  "ssm:LabelParameterVersion","ssm:AddTagsToResource"],"Resource":"$P/yct/owner/*"},
{"Effect":"Deny","Action":["ssm:GetParameter","ssm:GetParameters","ssm:GetParameterHistory",
  "ssm:GetParametersByPath"],"Resource":"$P/yct/owner/age_key"}
EOF
)
cat > "$TMP/pod.json" <<EOF
{"Version":"2012-10-17","Statement":[ $GUARD,
 {"Effect":"Allow","Action":["ssm:GetParameter"],"Resource":"$P/yct/hf_token"},
 {"Effect":"Allow","Action":["kms:Decrypt"],"Resource":"*",
  "Condition":{"StringEquals":{"kms:ViaService":"ssm.eu-central-1.amazonaws.com"}}} ]}
EOF
cat > "$TMP/mgr.json" <<EOF
{"Version":"2012-10-17","Statement":[ $GUARD,
 {"Effect":"Deny","Action":["ssm:GetParameter","ssm:GetParameters","ssm:GetParameterHistory"],
  "Resource":"$P/yct/hf_token"} ]}
EOF
aws iam put-role-policy --role-name "$ROLE" --policy-name yct-pod-params --policy-document "file://$TMP/pod.json"
aws iam put-user-policy --user-name tribe-pod-manager --policy-name yct-owner-guard --policy-document "file://$TMP/mgr.json"
echo "  pod: reads hf_token + owner decisions; cannot write /yct/owner/* or read age_key"
echo "  tribe-pod-manager (Claude): reads owner decisions only; no hf_token, no age_key, no writes"
echo
echo "DONE. Tell Claude: owner setup done.  (Delete this file now: it contains your HF token.)"
