# AlloVoice on Oracle Always Free — setup guide

## 0. Console access (you, in browser)
1. Log into cloud.oracle.com (tenancy name from the welcome email).
2. Home region **UK South (London)** — set once, cannot change.

## 1. Network (console, one time)
- Networking > Virtual Cloud Networks > **Create VCN** (default, with Internet Gateway).
- Security list: add Ingress rules for `0.0.0.0/0` on **TCP 80** and **TCP 443**
  (SSH 22 is open by default).

## 2. SSH key (your laptop)
- `ssh-keygen -t ed25519 -f ~/.ssh/id_allovoice` (no passphrase or one you store safe).

## 3. Land the box
- Try console first: Compute > Instances > Create — shape **VM.Standard.A1.Flex**,
  **1 OCPU / 6 GB**, image **Ubuntu 24.04 ARM**, paste the `.pub` key.
- If "Out of capacity": run `python3 launch_retry.py` (see file header) and wait.
- Resize to 2 OCPU / 12 GB later (Instance > More actions > Edit, shape).

## 4. Server setup (SSH in as ubuntu)
- `sudo bash setup.sh`, then log out and back in.
- `git clone <AlloVoice repo> /opt/allovoice` (or scp the folder).

## 5. DNS (free, no domain purchase)
- duckdns.org > create `allovoice` subdomain > point A record at the instance public IP.
- Put `https://allovoice.duckdns.org` in `.env.prod` (DOMAIN + PUBLIC_API_URL + CORS).

## 6. Launch
- `cd /opt/allovoice/deploy/oracle`
- `cp .env.prod.example .env.prod` and fill it (Aiven URL from backend/.env,
  R2 keys, fresh `openssl rand -hex 32` JWT, our Groq key).
- `DOMAIN=allovoice.duckdns.org docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build`
- Check: `https://allovoice.duckdns.org/api/health` → ok.

## Notes
- Aiven free = 20 connections: pool stays at 3+2 (already in compose).
- First boot downloads images (~5 min). Caddy issues TLS automatically.
- Never provision non-Free shapes; never click upgrade to Pay As You Go.
