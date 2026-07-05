# Deploy to Oracle Cloud (Always Free, all-in-one)

Runs the whole thing 24/7 on a free Oracle VM: daily auto-posting (cron),
the dashboard, and the ngrok fixed-URL tunnel — surviving reboots via systemd.
Your PC can be off.

## 1. Create the VM (one time)
1. Sign up at https://cloud.oracle.com (Always Free; needs a card for verification,
   not charged).
2. **Compute → Instances → Create instance**:
   - Image: **Ubuntu 22.04**
   - Shape: **Ampere (VM.Standard.A1.Flex)** — e.g. 2 OCPU / 12 GB (ARM, recommended,
     strongest free option). If A1 capacity is unavailable, use
     **VM.Standard.E2.1.Micro** (AMD x86, smaller).
   - Add your SSH public key.
3. Note the **public IP**. No need to open any ports — we use ngrok (outbound only).

## 2. Get the code onto the VM
On your **local** machine:
```bash
bash deploy/make-bundle.sh          # makes /tmp/fb-anime-pipeline.tgz (no footage/secrets)
scp /tmp/fb-anime-pipeline.tgz ubuntu@<VM_PUBLIC_IP>:~/
```
On the **VM** (SSH in: `ssh ubuntu@<VM_PUBLIC_IP>`):
```bash
mkdir -p ~/fb-anime-pipeline && tar xzf ~/fb-anime-pipeline.tgz -C ~/fb-anime-pipeline
cd ~/fb-anime-pipeline
```

## 3. Provision (installs tools, re-downloads footage from recorded sources)
```bash
bash deploy/bootstrap.sh
```
Auto-detects ARM vs x86 and installs ffmpeg, piper (+voice), yt-dlp, ngrok into
`~/.local`, fixes `config.json` paths, sets timezone to Asia/Singapore, and pulls
footage from each topic's `source:` URL.

## 4. Secrets + ngrok auth
```bash
cp secrets.env.example secrets.env
nano secrets.env        # fill: per-channel FB_PAGE_ID/_TOKEN, DASHBOARD_USER/PASS, NGROK_DOMAIN
ngrok config add-authtoken <YOUR_NGROK_TOKEN>
```
> Use the **same** ngrok account that reserved `NGROK_DOMAIN`. ngrok free allows one
> active agent — so don't also run the tunnel on your PC at the same time.

## 5. Start everything
```bash
bash deploy/install-services.sh
```
Enables `donghua-dashboard` + `donghua-ngrok` services and the 20:00 cron. Dashboard
goes live at `https://<NGROK_DOMAIN>`.

## Operate
```bash
systemctl status donghua-dashboard donghua-ngrok
journalctl -u donghua-dashboard -f      # dashboard logs
journalctl -u donghua-ngrok -f          # tunnel logs (also prints the URL)
crontab -l                              # the daily-post job
```
Update code later: re-run `make-bundle.sh` + scp + untar, then
`sudo systemctl restart donghua-dashboard donghua-ngrok`.

## Notes
- **No Oracle firewall changes needed** — ngrok dials out. (If you ever bind the
  dashboard to a public port instead, you must open it in BOTH the VCN security list
  and the instance's iptables — easy to get wrong; the tunnel avoids all that.)
- FB tokens live in `secrets.env` on the VM (private, gitignored). Keep the VM locked
  down to your SSH key.
- `posted.json` markers travel in the bundle, so the cloud box won't re-post what was
  already posted locally.
