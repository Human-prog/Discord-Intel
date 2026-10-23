# Discord setup — Discord Project Intelligence

The bot is the write path into the system: projects are registered from
Discord, notes and health snapshots are recorded there, and the mobile
dashboard is a read-only view of the same database.

The bot uses **no privileged intents** (no message content, no member list)
and every reply is ephemeral. A configured token without explicit owner IDs is
refused at startup (fail closed).

## 1. Create the Discord application and bot

1. Open <https://discord.com/developers/applications> and create a new
   application.
2. Open **Bot** → **Add Bot** if one does not exist.
3. Reset and copy the token once. **Never paste it into chat, a commit, or a
   command line** — write it directly into `/etc/dpi/.env` on `home3013`.
4. Leave every **Privileged Gateway Intent** disabled.

## 2. Invite the bot to your server

1. Open **OAuth2 → URL Generator**.
2. Scopes: `bot` and `applications.commands`.
3. Bot permissions: `Send Messages` is sufficient (the bot only replies
   ephemerally; add `Embed Links` if you later change reply formats).
4. Open the generated URL, choose your server, and authorize.

## 3. Collect the numeric IDs

In the Discord client: **Settings → Advanced → Developer Mode** on, then use
**Copy ID**:

| Value | Where | `.env` variable |
|---|---|---|
| Your user ID | right-click your avatar | `DISCORD_OWNER_USER_IDS` |
| Server ID | right-click the server icon | `DISCORD_ALLOWED_GUILD_IDS` |
| Channel ID | right-click the channel | `DISCORD_ALLOWED_CHANNEL_IDS` |

At least one owner ID is required. The guild and channel allowlists are
enforced on every command, so list all channels where the bot may be used. You
can add several IDs comma-separated.

## 4. Configure the server

Edit `/etc/dpi/.env` as root (for example with `sudoedit /etc/dpi/.env`) and add
or update:

```dotenv
DISCORD_BOT_TOKEN=<token from step 1>
DISCORD_OWNER_USER_IDS=<your user ID>
DISCORD_ALLOWED_GUILD_IDS=<server ID>
DISCORD_ALLOWED_CHANNEL_IDS=<channel ID>
DISCORD_ALLOW_DMS=false
PROJECT_ALLOWED_ROOTS=/opt/dpi/app
```

`PROJECT_ALLOWED_ROOTS` lists the absolute directories a project may point at.
Add more comma-separated roots only for directories you want the health engine
to inspect; the bot cannot register anything outside this list.

Optional research settings (local research works without either of these):

```dotenv
RESEARCH_PROVIDER=tavily          # none | tavily | brave
RESEARCH_API_KEY=<provider key>
DASHBOARD_PUBLIC_URL=https://home3013.tail53635c.ts.net
```

`DASHBOARD_PUBLIC_URL` is tailnet-only and is used for the “full report” link
in Discord replies. Keep `RESEARCH_ALLOWED_DOMAINS` empty to let the provider
choose domains, or set a comma-separated allowlist to restrict web fetching.

Keep the file at mode `0640`, owner `root`, group `dpi`:

```bash
sudo chown root:dpi /etc/dpi/.env
sudo chmod 0640 /etc/dpi/.env
```

## 5. Install and start the bot service

```bash
sudo cp /opt/dpi/app/deploy/systemd/discord-project-intelligence-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now discord-project-intelligence-bot
sudo systemctl status discord-project-intelligence-bot --no-pager -l
sudo journalctl -u discord-project-intelligence-bot -n 40 --no-pager
```

The startup log shows `Bot ready as <name>`; it never prints the token. The
dashboard service and the bot service are independent:

```bash
sudo systemctl restart discord-project-intelligence-bot
sudo systemctl stop discord-project-intelligence-bot
```

## 6. Register the first project

In the allowlisted channel, run:

```text
/help
/create-project name:Discord Project Intelligence root:/opt/dpi/app description:Private project intelligence system
```

The owner-only command validates the path against `PROJECT_ALLOWED_ROOTS`,
registers the project, and maps every project command to that channel. If the
directory is already registered it is connected instead of duplicated.

Then refresh `https://home3013.tail53635c.ts.net` — the project appears on the
dashboard. Useful follow-ups:

| Command | Effect |
|---|---|
| `/health` | Runs a read-only Git health check and stores a snapshot |
| `/note content:...` | Adds a note that shows up in dashboard activity |
| `/roadmap` | Lists milestones for the mapped project |
| `/research question:... scope:local\|web\|both` | Runs a cited research job; `both` still completes with local results when web is not configured |
| `/connect-project project_id:<id>` | Maps an existing project to another channel |

`/research` uses the project mapped to the current channel unless
`project_id` is supplied. It defers the reply, then posts a compact report with
citation keys such as `project:3`, `note:12`, or `work:44`. The full report is
saved in the dashboard and linked as `#research-<job_id>`. Ask for `scope:local`
to keep the job entirely on the server; `scope:web` fails closed when no
provider and API key are configured.

## 7. Troubleshooting

- **Commands do not appear in Discord** — the bot syncs guild-scoped commands
  at startup for each ID in `DISCORD_ALLOWED_GUILD_IDS`; confirm the server ID
  and restart the service. Restarting the Discord client forces a refresh.
- **`Authentication failed` on every command** — the user ID is missing from
  `DISCORD_OWNER_USER_IDS`, or the channel is not in
  `DISCORD_ALLOWED_CHANNEL_IDS`.
- **`Refusing to create the project`** — the resolved path is outside
  `PROJECT_ALLOWED_ROOTS` or does not exist as a directory readable by `dpi`.
- **`Web research is not configured`** — set `RESEARCH_PROVIDER` to `tavily`
  or `brave` and add `RESEARCH_API_KEY` in `/etc/dpi/.env`, then restart the
  bot. Use `scope:local` (or plain `/research` with no provider) to search the
  imported catalog, notes, and work history without external access.
- **Service exits immediately** — inspect
  `journalctl -u discord-project-intelligence-bot -n 50 --no-pager`. The most
  common causes are a token without owner IDs, an invalid token, or a missing
  `/etc/dpi/.env`.
