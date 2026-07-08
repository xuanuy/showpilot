# Deploy to Alibaba Cloud ECS (hackathon target)

**Live deployment:** the hackathon backend runs on ECS instance
`i-t4nahwvwjumrnkdbr23t` (`ecs.e-c1m2.large`, Ubuntu 22.04, ap-southeast-1a) —
ops dashboard at https://subjugable-alecia-trifacial.ngrok-free.dev (Basic Auth).
Provisioned entirely via the Alibaba Cloud CLI: see [`provision.sh`](provision.sh).
Model APIs (Qwen chat + Wan text-to-video) are Alibaba Cloud Model Studio
endpoints — clients in [`lib/qwen.py`](../../lib/qwen.py) and
[`lib/wan.py`](../../lib/wan.py).

Runs ShowPilot 24/7 on an Alibaba Cloud ECS instance: daily auto-posting (cron),
the dashboard, and the ngrok fixed-URL tunnel — surviving reboots via systemd.
Reuses the generic Linux bundle in `deploy/` (bootstrap + systemd units).

## 1. Create the ECS instance (one time)
1. Sign in at https://ecs.console.aliyun.com (hackathon voucher credits apply).
2. **Create Instance**:
   - Region: **Singapore (ap-southeast-1)** — same region as the Qwen Cloud
     `dashscope-intl` endpoint, lowest latency.
   - Image: **Ubuntu 22.04 64-bit**
   - Instance type: `ecs.e-c1m2.large` (2 vCPU / 4 GB) is plenty; burstable
     `ecs.t6-c1m2.large` also works.
   - System disk: 40 GB ESSD.
   - Add your SSH public key. Assign a public IP (pay-by-traffic is fine).
3. No inbound ports needed beyond SSH (22) — dashboard is exposed via ngrok
   (outbound only), so the default security group is fine.

## 2. Get the code onto the instance
On your **local** machine:
```bash
bash deploy/make-bundle.sh          # makes /tmp/fb-anime-pipeline.tgz (no footage/secrets)
scp /tmp/fb-anime-pipeline.tgz root@<ECS_PUBLIC_IP>:~/
```
On the **instance** (`ssh root@<ECS_PUBLIC_IP>`, then `adduser show && su - show`
or just run as root):
```bash
mkdir -p ~/showpilot && tar xzf ~/fb-anime-pipeline.tgz -C ~/showpilot
cd ~/showpilot
```

## 3. Provision
```bash
bash deploy/bootstrap.sh
```
Auto-detects ARM vs x86 and installs ffmpeg, piper (+voice), yt-dlp, ngrok into
`~/.local`, fixes `config.json` paths, and sets timezone to Asia/Singapore.

## 4. Secrets
```bash
cp secrets.env.example secrets.env && nano secrets.env
```
Minimum for the hackathon demo:
- `DASHSCOPE_API_KEY` — from qwencloud.com → API Keys (enables Qwen scripts +
  Wan `mode: wan` video generation)
- one channel's `_PAGE_ID` / `_TOKEN` pair for publishing
- `DASHBOARD_USER` / `DASHBOARD_PASS` if exposing the dashboard

## 5. Services + daily schedule
```bash
bash deploy/install-services.sh
```
Installs the systemd units (dashboard + ngrok) and the daily `all-channels`
cron. Verify with:
```bash
systemctl status donghua-dashboard
python3 pipeline.py build donghua-realm the-sword-that-refused.md   # Wan demo topic
```

## Notes
- Wan tasks are async (1–5 min per shot); generated shots are cached under
  `channels/<id>/build/<topic>/wan/` so a re-run never re-spends credits.
- Video URLs returned by Wan expire in 24 h — the pipeline downloads each shot
  immediately, so nothing depends on the URL after a build.
