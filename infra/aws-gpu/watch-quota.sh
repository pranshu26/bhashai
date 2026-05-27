#!/usr/bin/env bash
# Poll AWS service-quotas every 5 min until the Running On-Demand G/VT quota is ≥ 4 vCPUs
# (enough for g6e.xlarge). Exits 0 when approved, 1 if the wait runs past MAX_HOURS.
#
# Usage:
#   AWS_PROFILE=bhashai bash infra/aws-gpu/watch-quota.sh
#   # or run in background and pipe to a notify-me script:
#   bash infra/aws-gpu/watch-quota.sh && say "BhashAI quota approved" && open https://example.com

set -euo pipefail

REGION="${AWS_REGION:-eu-north-1}"
ON_DEMAND_QUOTA_CODE="L-DB2E81BA"
SPOT_QUOTA_CODE="L-3819A6DF"
INTERVAL="${INTERVAL:-300}"           # seconds between polls
MAX_HOURS="${MAX_HOURS:-6}"           # give up after this many hours

deadline=$(( $(date +%s) + MAX_HOURS * 3600 ))

while :; do
  od=$(aws --region "$REGION" service-quotas get-service-quota \
       --service-code ec2 --quota-code "$ON_DEMAND_QUOTA_CODE" \
       --query 'Quota.Value' --output text 2>/dev/null || echo "0")
  sp=$(aws --region "$REGION" service-quotas get-service-quota \
       --service-code ec2 --quota-code "$SPOT_QUOTA_CODE" \
       --query 'Quota.Value' --output text 2>/dev/null || echo "0")
  ts=$(date '+%Y-%m-%d %H:%M:%S')
  echo "[$ts]  on-demand G/VT vCPUs = ${od}    spot G/VT vCPUs = ${sp}"

  # 4 vCPUs covers g6e.xlarge; user picked on-demand for the first launch.
  if awk -v v="$od" 'BEGIN { exit !(v+0 >= 4) }'; then
    echo "[$ts]  ✓ on-demand approved (≥4 vCPUs). Run infra/aws-gpu/launch.sh now."
    exit 0
  fi

  if [[ $(date +%s) -ge $deadline ]]; then
    echo "[$ts]  ✗ giving up after ${MAX_HOURS}h. Open https://eu-north-1.console.aws.amazon.com/servicequotas/home/services/ec2/quotas/L-DB2E81BA to check by hand."
    exit 1
  fi
  sleep "$INTERVAL"
done
