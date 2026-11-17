#!/usr/bin/env bash
# Run a shell command on the project EC2 pod via SSM (no SSH / public IP needed).
# Usage: infra/pod_exec.sh 'command string' [timeout_seconds]
# Pod id is read from infra/pod.env (POD_INSTANCE_ID=...). Secrets are never echoed.
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
# shellcheck disable=SC1091
source "$here/pod.env"
cmd="$1"; timeout="${2:-3600}"
params=$(python3 -c 'import json,sys; print(json.dumps({"commands":[sys.argv[1]],"executionTimeout":[sys.argv[2]]}))' "$cmd" "$timeout")
cid=$(aws ssm send-command --instance-ids "$POD_INSTANCE_ID" --document-name AWS-RunShellScript \
      --parameters "$params" --timeout-seconds 60 --query Command.CommandId --output text)
while :; do
  st=$(aws ssm get-command-invocation --command-id "$cid" --instance-id "$POD_INSTANCE_ID" --query Status --output text 2>/dev/null || echo Pending)
  case "$st" in Pending|InProgress|Delayed) sleep 3;; *) break;; esac
done
aws ssm get-command-invocation --command-id "$cid" --instance-id "$POD_INSTANCE_ID" --query StandardOutputContent --output text
err=$(aws ssm get-command-invocation --command-id "$cid" --instance-id "$POD_INSTANCE_ID" --query StandardErrorContent --output text)
[ -n "$err" ] && [ "$err" != "None" ] && echo "--- stderr ---" >&2 && echo "$err" >&2
[ "$st" = "Success" ]
