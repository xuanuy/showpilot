# Run on a Mac (Intel) 24/7 — free home server

Turns your MacBook Pro into the always-on host: dashboard + ngrok fixed URL + daily
auto-posting, surviving reboots via launchd. ~$2-4/month electricity, and the battery
acts as a mini-UPS. No router/port config (ngrok dials out).

## 1. Get the code onto the Mac
On your **WSL** machine: `bash deploy/make-bundle.sh` → `/tmp/fb-anime-pipeline.tgz`.
Move it to the Mac (AirDrop / USB / scp), then on the Mac Terminal:
```bash
mkdir -p ~/fb-anime-pipeline && tar xzf ~/Downloads/fb-anime-pipeline.tgz -C ~/fb-anime-pipeline
cd ~/fb-anime-pipeline
```

## 2. Provision
```bash
bash deploy/mac/bootstrap-mac.sh
```
Installs ffmpeg/piper/yt-dlp/ngrok (Intel mac builds) into `~/.local`, clears Gatekeeper
quarantine, fixes `config.json`, and re-downloads footage from each topic's `source:`.
> If it says python3 is missing: `xcode-select --install`, then re-run.

## 3. Secrets + ngrok
```bash
cp secrets.env.example secrets.env
nano secrets.env      # FB_PAGE_ID/_TOKEN per channel, DASHBOARD_USER/PASS, NGROK_DOMAIN
~/.local/bin/ngrok config add-authtoken <YOUR_NGROK_TOKEN>
```

## 4. Start the services
```bash
bash deploy/mac/install-mac.sh
```
Loads launchd agents: dashboard, ngrok, daily-post (20:00), caffeinate. Dashboard live
at `https://<NGROK_DOMAIN>`.

## 5. Keep it always-on (important for a laptop)
- **Plug it in** and keep it on power.
- **Lid open** → the caffeinate agent prevents sleep. For **lid-closed** operation:
  `sudo pmset -c disablesleep 1`
- **System Settings → Users & Groups → Automatic login: ON** so the agents relaunch
  after a reboot/power blip.
- Don't run ngrok anywhere else (free plan = one agent).

## Operate
```bash
launchctl list | grep donghua            # see loaded agents
tail -f /tmp/donghua-dashboard.log       # dashboard log
tail -f /tmp/donghua-ngrok.log           # tunnel log
cat cron.log                             # daily-post output
```
Stop one: `launchctl unload ~/Library/LaunchAgents/com.donghua.dashboard.plist`
Update code: re-bundle + replace files, then `launchctl unload/load` the agents (or reboot).

## Notes
- Short ffmpeg bursts won't sustain-throttle the 2018 i7; encoding a 40s clip is quick.
- FB tokens live in `secrets.env` on your Mac (private). Fine for a personal machine.
