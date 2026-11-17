#!/usr/bin/env bash
# YCT owner setup — paste into AWS CloudShell (region eu-central-1), signed in as the account admin.
# Nothing is installed on your Mac. Secrets go only to SSM Parameter Store (SecureString).
#  - /yct/hf_token          SecureString  readable by the pod role ONLY
#  - /yct/owner/age_key     SecureString  readable by NOBODY but you (until you release it at unblinding)
#  - /yct/owner/age_pub     String        public key the Curator encrypts labels to
#  - /yct/owner/budget_usd  String        GPU budget cap
#  - /yct/owner/data_decision, /yct/owner/owner_arn  String
# The pod role and the tribe-pod-manager user get read-only access to /yct/owner/* (except age_key)
# and an explicit DENY on writing /yct/owner/*, so only you can perform human-only actions.
set -euo pipefail
export AWS_DEFAULT_REGION=eu-central-1
umask 077
ACCT=$(aws sts get-caller-identity --query Account --output text)
ME=$(aws sts get-caller-identity --query Arn --output text)
ROLE=$(aws iam get-instance-profile --instance-profile-name t3code-gpu-ssm-profile \
       --query 'InstanceProfile.Roles[0].RoleName' --output text)
P="arn:aws:ssm:eu-central-1:$ACCT:parameter"
echo "Owner identity: $ME   Pod role: $ROLE"

put() {  # put <name> <type> <value>  (value via file, never on the command line)
  f=$(mktemp); jq -n --arg n "$1" --arg t "$2" --arg v "$3" \
     '{Name:$n,Type:$t,Value:$v,Overwrite:true}' > "$f"
  aws ssm put-parameter --cli-input-json "file://$f" >/dev/null; rm -f "$f"; echo "  set $1"
}

echo; echo "== 1. Hugging Face token =="
echo "First: accept the licence at https://huggingface.co/meta-llama/Llama-3.2-3B"
echo "Then create a fine-grained token with ONLY 'Read access to contents of all public gated repos you can access'."
read -r -s -p "Paste HF token (hidden): " HF; echo
curl -fsS -H "Authorization: Bearer $HF" https://huggingface.co/api/whoami-v2 >/dev/null || { echo "Token rejected"; exit 1; }
code=$(curl -s -o /dev/null -w '%{http_code}' -H "Authorization: Bearer $HF" \
       https://huggingface.co/meta-llama/Llama-3.2-3B/resolve/main/config.json)
[ "$code" = 200 ] && echo "  Llama-3.2-3B access: GRANTED" || echo "  Llama-3.2-3B access: PENDING (HTTP $code) — fine, re-check later"
put /yct/hf_token SecureString "$HF"; unset HF

echo; echo "== 2. Owner age key (seals outcome labels) =="
if ! aws ssm get-parameter --name /yct/owner/age_pub >/dev/null 2>&1; then
  mkdir -p ~/yct-age && curl -fsSL https://github.com/FiloSottile/age/releases/download/v1.2.1/age-v1.2.1-linux-amd64.tar.gz \
    | tar xz -C ~/yct-age
  KEY=$(~/yct-age/age/age-keygen 2>/dev/null)
  PUB=$(printf '%s\n' "$KEY" | ~/yct-age/age/age-keygen -y)
  put /yct/owner/age_key SecureString "$KEY"; unset KEY
  put /yct/owner/age_pub String "$PUB"
else echo "  age key already exists — kept"; fi

echo; echo "== 3. Owner decisions =="
put /yct/owner/owner_arn String "$ME"
put /yct/owner/budget_usd String "200"
put /yct/owner/data_decision String "SIGNED $(date -u +%F) by $ME: DATA_DECISION.md v2.2 §4 (repo commit 6c16d89)"

echo; echo "== 4. Permissions =="
READ_OWNER=$(jq -n --arg p "$P" '[ $p+"/yct/owner/age_pub", $p+"/yct/owner/budget_usd",
  $p+"/yct/owner/data_decision", $p+"/yct/owner/owner_arn", $p+"/yct/owner/unblind_token",
  $p+"/yct/owner/decisions" ]')
GUARD=$(jq -n --arg p "$P" --argjson ro "$READ_OWNER" '[
  {Effect:"Allow",Action:["ssm:GetParameter","ssm:GetParameterHistory"],Resource:$ro},
  {Effect:"Deny",Action:["ssm:PutParameter","ssm:DeleteParameter","ssm:DeleteParameters",
     "ssm:LabelParameterVersion","ssm:AddTagsToResource"],Resource:($p+"/yct/owner/*")},
  {Effect:"Deny",Action:["ssm:GetParameter","ssm:GetParameters","ssm:GetParameterHistory",
     "ssm:GetParametersByPath"],Resource:($p+"/yct/owner/age_key")}]')
POD=$(jq -n --arg p "$P" --argjson g "$GUARD" '{Version:"2012-10-17",Statement:($g + [
  {Effect:"Allow",Action:["ssm:GetParameter"],Resource:($p+"/yct/hf_token")},
  {Effect:"Allow",Action:["kms:Decrypt"],Resource:"*",
   Condition:{StringEquals:{"kms:ViaService":"ssm.eu-central-1.amazonaws.com"}}}])}')
MGR=$(jq -n --arg p "$P" --argjson g "$GUARD" '{Version:"2012-10-17",Statement:($g + [
  {Effect:"Deny",Action:["ssm:GetParameter","ssm:GetParameters","ssm:GetParameterHistory"],
   Resource:($p+"/yct/hf_token")}])}')
aws iam put-role-policy --role-name "$ROLE" --policy-name yct-pod-params --policy-document "$POD"
aws iam put-user-policy --user-name tribe-pod-manager --policy-name yct-owner-guard --policy-document "$MGR"
echo "  pod role: reads hf_token + owner decisions; cannot write /yct/owner/* or read age_key"
echo "  tribe-pod-manager: reads owner decisions; cannot write them, cannot read hf_token or age_key"

echo; echo "DONE. Tell Claude: 'owner setup done'. Keep this CloudShell session's output; nothing secret was printed."
