#!/usr/bin/env bash
# AlloVoice Oracle setup — run ONCE on a fresh Ubuntu 24.04 ARM instance as ubuntu.
set -euo pipefail

sudo apt-get update
sudo apt-get install -y --no-install-recommends ca-certificates curl git ufw

# Docker (official repo, ARM build)
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker "$USER"

# Firewall: SSH + HTTP/S only (Caddy terminates TLS, so 8000/3000 stay internal).
sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

sudo mkdir -p /opt/allovoice
sudo chown "$USER:$USER" /opt/allovoice

echo "Setup done. Log out/in (docker group), clone the repo to /opt/allovoice, then see README.md."
