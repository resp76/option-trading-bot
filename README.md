# Option Trading Bot

This repository contains a configurable options trading bot (paper/live) with monitoring and Tradier adapter stubs.

## Getting started

Prereqs
- Linux (WSL fine)
- Python 3.11
- Git

1) Clone / open the repo

2) Create and activate venv

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

3) Configure credentials (do NOT paste API keys in chat)

Create a credentials file readable only by you:

```bash
mkdir -p ~/.config/option-bot
cat > ~/.config/option-bot/credentials.env <<'EOF'
export TRADIER_TOKEN="PASTE_YOUR_TOKEN_HERE"
export TRADIER_ACCOUNT_ID="YOUR_ACCOUNT_ID"
EOF
chmod 600 ~/.config/option-bot/credentials.env
source ~/.config/option-bot/credentials.env
```

Alternatively export the env vars in your shell directly:

```bash
export TRADIER_TOKEN="..."
export TRADIER_ACCOUNT_ID="..."
```

4) Run the bot

- Run a single scan cycle:

```
option-bot once
```

- Show the status summary:

```
option-bot status
```

- Start a background loop (writes to `run.log`):

```
option-bot start --background
```

- Stop the loop:

```
option-bot stop
```

## GitHub Actions (CI / scheduled monitor)

This repo includes a scheduled workflow that can run the monitor script. For GitHub Actions to run the monitor against Tradier, set repo secrets:

- `TRADIER_TOKEN`
- `TRADIER_ACCOUNT_ID`

Go to your repository > Settings > Secrets and variables > Actions and add these secrets. The workflow is configured to skip the monitor job when secrets are not set.

## Security
- Never commit API tokens or secrets. Use environment variables or GitHub Actions secrets.
- For production, run the bot under a dedicated user and use systemd or a supervised process.

## Troubleshooting
- If `option-bot` command isn’t found: ensure `pip install -e .` ran successfully in the repo venv.
- If API calls return 401/403: regenerate token in Tradier dashboard and update your env.

## License
MIT
