#!/usr/bin/env bash
# Driver-independent scheduled terminator (D-063 Q7, BUG-027 follow-up). Runs ON THE EC2 POD, fired by a
# systemd-run timer that the P4 driver schedules right after each launch, at deadline + 15 min
# (infra/lambda_gpu.py pod_terminator_script). Lambda bills a halted box until it is TERMINATED, so the box's
# own dead-man shutdown is not enough; this terminates the instance even if the driver, its container and
# the session are gone. The Lambda key is read from SSM at fire time into this process's environment only
# (never argv, never printed); the pod role needs ssm:GetParameter on it (owner-created SecureString).
# Usage: gpu_terminator.sh INSTANCE_ID MARGIN_S INFRA_DIR
set -euo pipefail
IID="${1:?instance id}"; MARGIN="${2:?margin s}"; INFRA="${3:?infra dir}"
PARAM="${YCT_LAMBDA_KEY_PARAM:-/yct/lambda_api_key}"
LAMBDA_API_KEY="$(aws ssm get-parameter --region eu-central-1 --name "$PARAM" --with-decryption \
  --query Parameter.Value --output text)"
export LAMBDA_API_KEY
exec python3 "$INFRA/lambda_gpu.py" reap-deadline --margin-s "$MARGIN" --id "$IID"
