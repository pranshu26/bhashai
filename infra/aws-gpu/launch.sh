#!/usr/bin/env bash
# Launch the BhashAI GPU box on AWS. Run AFTER watch-quota.sh exits 0.
#
# Secrets stay on YOUR laptop — this script doesn't put HF_TOKEN/API_KEY in
# the instance metadata (anyone with ec2:DescribeInstances could read it).
# You SSH in and run bootstrap.sh by hand with the secrets in your shell.
#
# Override anything with env vars:
#   INSTANCE_TYPE  (default g6e.xlarge)
#   AMI_ID         (default: NVIDIA DLAMI Ubuntu 22.04 latest as of 2026-05-21)
#   SUBNET_ID      (default eu-north-1a subnet)
#   SG_ID          (default bhashai-sg)
#   KEY_NAME       (default bhashai)
#   AWS_PROFILE    (default current shell's profile)
#   AWS_REGION     (default eu-north-1)

set -euo pipefail

INSTANCE_TYPE="${INSTANCE_TYPE:-g6e.xlarge}"
AMI_ID="${AMI_ID:-ami-046a09eaf6dd419ae}"
SUBNET_ID="${SUBNET_ID:-subnet-0dfb7fa5030a982a6}"
SG_ID="${SG_ID:-sg-0bf4e3ddb40a2cd43}"
KEY_NAME="${KEY_NAME:-bhashai}"
REGION="${AWS_REGION:-eu-north-1}"

echo "==> Checking quota (need ≥ 4 vCPUs of Running On-Demand G/VT)"
QUOTA=$(aws --region "$REGION" service-quotas get-service-quota \
  --service-code ec2 --quota-code L-DB2E81BA --query 'Quota.Value' --output text)
echo "    current quota: $QUOTA"
if awk -v v="$QUOTA" 'BEGIN { exit !(v+0 < 4) }'; then
  echo "    ✗ quota too low. Wait for AWS approval (watch-quota.sh) before launching."
  exit 1
fi

echo "==> Launching $INSTANCE_TYPE in $REGION"
OUT=$(aws --region "$REGION" ec2 run-instances \
  --image-id "$AMI_ID" \
  --instance-type "$INSTANCE_TYPE" \
  --key-name "$KEY_NAME" \
  --subnet-id "$SUBNET_ID" \
  --security-group-ids "$SG_ID" \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=200,VolumeType=gp3,DeleteOnTermination=true}' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=bhashai-gpu}]' \
  --output json)

INSTANCE_ID=$(echo "$OUT" | python3 -c "import sys,json;print(json.load(sys.stdin)['Instances'][0]['InstanceId'])")
echo "    instance: $INSTANCE_ID"
echo "==> Waiting for running state..."
aws --region "$REGION" ec2 wait instance-running --instance-ids "$INSTANCE_ID"

IP=$(aws --region "$REGION" ec2 describe-instances --instance-ids "$INSTANCE_ID" \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text)

MY_IP=$(curl -fsS https://checkip.amazonaws.com 2>/dev/null | tr -d '[:space:]' || echo "")
SG_ALLOWS_MY_SSH=""
if [[ -n "$MY_IP" ]]; then
  ALLOWED=$(aws --region "$REGION" ec2 describe-security-groups --group-ids "$SG_ID" \
    --query "SecurityGroups[0].IpPermissions[?FromPort==\`22\`].IpRanges[].CidrIp" --output text)
  if [[ "$ALLOWED" == *"${MY_IP}/32"* ]]; then
    SG_ALLOWS_MY_SSH="yes"
  fi
fi

cat <<INFO

================================================================================
✓ Launched

  Instance: $INSTANCE_ID
  IP:       $IP
  SSH:      ssh -i ~/.ssh/${KEY_NAME}.pem ubuntu@$IP

INFO

if [[ -n "$MY_IP" && -z "$SG_ALLOWS_MY_SSH" ]]; then
  cat <<INFO
  ⚠  Your current IP ($MY_IP) is NOT in $SG_ID's port-22 allow list. SSH will
     time out. To open it just for you:

     aws --region $REGION ec2 authorize-security-group-ingress \\
       --group-id $SG_ID --protocol tcp --port 22 --cidr ${MY_IP}/32

INFO
fi

cat <<'INFO'
Next steps (on the new GPU box):

  ssh -i ~/.ssh/bhashai.pem ubuntu@<IP>
  sudo apt-get update && sudo apt-get install -y git
  git clone https://github.com/pranshu26/bhashai.git
  cd bhashai/infra/aws-gpu
  export API_KEY="$(openssl rand -hex 32)"
  export HF_TOKEN="<paste your HuggingFace token>"
  export MODEL_TIER=awq
  sudo -E bash bootstrap.sh        # ~25-40 min on first run

When bootstrap finishes it prints the env block to paste into your existing
EC2 parser-service .env on 16.171.29.33, then `pm2 restart bhashai-parser
bhashai-worker`.

To kill the GPU box later:
  aws --region eu-north-1 ec2 terminate-instances --instance-ids INSTANCE_ID_HERE
================================================================================
INFO
