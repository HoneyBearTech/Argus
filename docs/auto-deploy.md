# Auto-deploy (source mode)

A server that runs Argus from a checkout ([source mode](upgrading.md#running-from-a-checkout-source-mode))
can follow `main` by itself: a systemd timer runs [`scripts/auto_deploy.py`](../scripts/auto_deploy.py) every five
minutes. Nothing reaches into the server; it only makes outbound HTTPS requests to GitHub (and to Discord,
if configured).

## What a run does

1. Fetches `origin/main`. If the checkout is already there, isn't on `main` (for example because you
   checked out a release tag), or has local edits to tracked files or commits of its own, it stops and
   changes nothing. Untracked and gitignored files (`.env`, `targets/`, `secrets/`) don't count.
2. Asks GitHub's API whether the **Dashboards + config** check from GitHub Actions passed on the new
   commit. While it's running, the timer waits; a commit where it failed is never deployed.
3. Fast-forwards, runs `docker compose up -d --build`, and restarts the services whose bind-mounted
   configuration changed: `prometheus/` → Prometheus, `blackbox/` → blackbox, `provisioning/` → Grafana,
   `logs/loki.yaml` → Loki (if it runs here). Dashboard changes need no restart.
4. Waits up to five minutes for Grafana (`/api/health`) and Prometheus (`/-/ready`) to answer on their
   published ports (sending Prometheus' password from `secrets/prometheus_password`, in case it
   [requires one](security.md#requiring-a-password-for-prometheus)). If they don't, or a step fails, it **rolls back** to the previous commit, redeploys
   it, and records the bad commit in `.git/argus-deploy-bad-commits` so later runs skip it until `main`
   moves on.

If `DISCORD_WEBHOOK_URL` is set in `.env`, every deploy and rollback is posted to that channel. Everything
is also in the journal: `journalctl --user -u argus-deploy`.

## Installing

On the server, as the user that owns the checkout (it must be able to run `docker`). The unit assumes the
checkout is `~/Argus`; edit `WorkingDirectory` and `ExecStart` if it's elsewhere.

```sh
cd ~/Argus
python3 scripts/auto_deploy.py --dry-run   # says what it would deploy; changes nothing
mkdir -p ~/.config/systemd/user
cp deploy/systemd/argus-deploy.service deploy/systemd/argus-deploy.timer ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now argus-deploy.timer
sudo loginctl enable-linger "$USER"         # keep user timers running when nobody is logged in
systemctl --user list-timers argus-deploy.timer
```

To pause it: `systemctl --user stop argus-deploy.timer` (`disable` to keep it off after a reboot). To
retry a commit that was rolled back, fix what broke, then delete its line from
`.git/argus-deploy-bad-commits`.

## What it trusts

Whoever can merge to `main` can change what runs on the server, as with a manual `git pull`. The script
deploys only commits that are on `main` on GitHub, fetched over HTTPS, and only after the required check
has passed; it accepts that check only from the GitHub Actions app. GitHub's API is used without a token
(60 requests an hour, and a run asks only when there's a new commit). Branch protection on `main`, which
requires that check, is what keeps an untested change from reaching the server.
