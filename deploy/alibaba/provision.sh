#!/usr/bin/env bash
# Provision the ShowPilot backend on Alibaba Cloud ECS via the aliyun CLI.
# These are the exact calls used to create the live hackathon instance
# (i-t4napguee3ywqzzqpy4y, ap-southeast-1a, 8.222.216.29 — dashboard at
# https://subjugable-alecia-trifacial.ngrok-free.dev behind Basic Auth).
#
# Prereqs: aliyun CLI (https://github.com/aliyun/aliyun-cli) configured with a
# RAM AccessKey:  aliyun configure set --profile showpilot --mode AK \
#                   --access-key-id ... --access-key-secret ... --region ap-southeast-1
set -euo pipefail
P="--profile showpilot"
REGION=ap-southeast-1
ZONE=${ZONE:-ap-southeast-1a}
TYPE=${TYPE:-ecs.e-c1m2.large}                      # 2 vCPU / 4 GB economy
IMAGE=${IMAGE:-ubuntu_22_04_x64_20G_alibase_20260615.vhd}

echo "== VPC + VSwitch =="
VPC=$(aliyun $P vpc CreateVpc --RegionId $REGION --CidrBlock 192.168.0.0/16 \
      --VpcName showpilot-vpc | grep -oP '(?<="VpcId": ")[^"]*')
sleep 5
VSW=$(aliyun $P vpc CreateVSwitch --RegionId $REGION --ZoneId $ZONE --VpcId "$VPC" \
      --CidrBlock 192.168.1.0/24 --VSwitchName showpilot-vsw | grep -oP '(?<="VSwitchId": ")[^"]*')

echo "== Security group (SSH only; dashboard is exposed via outbound tunnel) =="
SG=$(aliyun $P ecs CreateSecurityGroup --RegionId $REGION --VpcId "$VPC" \
     --SecurityGroupName showpilot-sg --Description "SSH only" | grep -oP '(?<="SecurityGroupId": ")[^"]*')
aliyun $P ecs AuthorizeSecurityGroup --RegionId $REGION --SecurityGroupId "$SG" \
    --IpProtocol tcp --PortRange 22/22 --SourceCidrIp 0.0.0.0/0 --Description ssh >/dev/null

echo "== SSH key (Alibaba ECS accepts RSA public keys) =="
[ -f ~/.ssh/showpilot_rsa ] || ssh-keygen -t rsa -b 4096 -N '' -C showpilot -f ~/.ssh/showpilot_rsa -q
aliyun $P ecs ImportKeyPair --RegionId $REGION --KeyPairName showpilot \
    --PublicKeyBody "$(cat ~/.ssh/showpilot_rsa.pub)" >/dev/null

echo "== ECS instance =="
ID=$(aliyun $P ecs RunInstances --RegionId $REGION --ZoneId $ZONE \
     --ImageId "$IMAGE" --InstanceType "$TYPE" \
     --SecurityGroupId "$SG" --VSwitchId "$VSW" \
     --InstanceName showpilot --HostName showpilot --KeyPairName showpilot \
     --InternetMaxBandwidthOut 5 --InternetChargeType PayByTraffic \
     --InstanceChargeType PostPaid \
     --SystemDisk.Category cloud_essd_entry --SystemDisk.Size 40 \
     | grep -oP '(?<=")i-[a-z0-9]+')

echo "instance: $ID — waiting for Running + public IP ..."
until aliyun $P ecs DescribeInstances --RegionId $REGION --InstanceIds "[\"$ID\"]" \
      | grep -q '"Status": "Running"'; do sleep 5; done
IP=$(aliyun $P ecs DescribeInstances --RegionId $REGION --InstanceIds "[\"$ID\"]" \
     | grep -A2 '"PublicIpAddress"' | grep -oP '\d+\.\d+\.\d+\.\d+' | head -1)

cat <<EOF

READY: root@$IP (key ~/.ssh/showpilot_rsa)

Next — ship the code and start the services (see README.md):
  bash deploy/make-bundle.sh
  scp -i ~/.ssh/showpilot_rsa /tmp/fb-anime-pipeline.tgz secrets.env root@$IP:~/
  ssh -i ~/.ssh/showpilot_rsa root@$IP \\
    'mkdir -p ~/showpilot && tar xzf fb-anime-pipeline.tgz -C ~/showpilot &&
     mv secrets.env ~/showpilot/ && cd ~/showpilot &&
     bash deploy/bootstrap.sh && bash deploy/install-services.sh'
EOF
