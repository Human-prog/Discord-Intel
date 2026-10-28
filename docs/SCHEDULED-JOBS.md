# Scheduled Jobs & Catalog Auto-Rescan Setup (v1.1.0)

## 1. Scheduled Research Job Setup

Enable the scheduled research job to run automatically. The `/schedule-research` command creates a DB entry; a background worker picks it up.

### Option A — Systemd timer (recommended)

Create `/etc/systemd/system/discord-project-intelligence-schedule.timer`:

```
[Unit]
Description=Discord Project Intelligence Scheduled Research

[Timer]
OnCalendar=*-*-* 02:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

And the service `/etc/systemd/system/discord-project-intelligence-schedule.service`:

```
[Unit]
Description=Run scheduled research jobs
After=discord-project-intelligence.service

[Service]
Type=oneshot
User=dpi
ExecStart=/opt/dpi/app/.venv/bin/python -c "
from project_intelligence.jobs.scheduler import Scheduler
s = Scheduler()
s.run_due_jobs()
"
WorkingDirectory=/opt/dpi/app
EnvironmentFile=/etc/dpi/.env
```

Enable:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now discord-project-intelligence-schedule.timer
```

### Option B — Crontab (simpler)

```bash
# As dpi user (or root with proper env)
crontab -e
# Add line:
0 2 * * * DPI_DATA_DIR=/var/lib/dpi/data /opt/dpi/app/.venv/bin/python -c "
from project_intelligence.jobs.scheduler import Scheduler; s=Scheduler(); s.run_due_jobs()
" >> /var/log/dpi/schedule.log 2>&1
```

---

## 2. Catalog Auto-Rescan Setup

Run the workstation scanner nightly:

```bash
# Crontab entry (as root or dpi with access to Windows path via mount / taildrop)
0 3 * * * DPI_DATA_DIR=/var/lib/dpi/data /opt/dpi/app/.venv/bin/python \
  /opt/dpi/app/scripts/catalog_projects.py >> /var/log/dpi/catalog_scan.log 2>&1
```

The script is idempotent — it only updates changed projects.

---

## 3. Monitor Log Files

```bash
tail -f /var/log/dpi/schedule.log
tail -f /var/log/dpi/catalog_scan.log
tail -f /opt/dpi/app/logs/bot.log
```
