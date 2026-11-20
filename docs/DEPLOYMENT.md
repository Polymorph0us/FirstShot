# FirstShot Deployment Guide

> **Target Architecture:** Local Private Instance (Workstation) + Tailscale Mesh Overlay + Optional Cloudflare Pages Demo

---

## 1. Private Local Deployment (systemd User Service)

Running FirstShot as a systemd user service ensures that the scheduler, blitz polling, and autonomous booking engine run reliably in the background across reboots.

### Step 1: Install Unit File

Copy or link the service unit into your user systemd directory:

```bash
mkdir -p ~/.config/systemd/user
cp /home/poly/Projects/FirstShot/backend/firstshot.service ~/.config/systemd/user/
```

### Step 2: Reload and Enable Service

```bash
systemctl --user daemon-reload
systemctl --user enable firstshot.service
systemctl --user start firstshot.service
```

### Step 3: Manage & Monitor

```bash
# Check status
systemctl --user status firstshot.service

# Stream live scheduler and booking logs
journalctl --user -u firstshot.service -f

# Restart service
systemctl --user restart firstshot.service
```

### Step 4: Ensure Lingering for Background Execution
To ensure user services remain active even when you log out of the desktop session:
```bash
loginctl enable-linger $USER
```

---

## 2. Remote Private Access via Tailscale

To monitor or arm FirstShot securely from your phone or another laptop without exposing ports to the public internet:

### Step 1: Install and Connect Tailscale

```bash
# Arch Linux
sudo pacman -S tailscale
sudo systemctl enable --now tailscaled
sudo tailscale up

# Debian / Ubuntu
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

### Step 2: Bind or Proxy to Tailscale IP

By default, the systemd service binds to `127.0.0.1`. You can either:
- Update `ExecStart` in `firstshot.service` to bind to your machine's Tailscale IP:
  ```ini
  ExecStart=/home/poly/Projects/FirstShot/backend/.venv/bin/uvicorn app.main:app --host 100.x.y.z --port 8000
  ```
  *(Replace `100.x.y.z` with your Tailscale IP from `tailscale ip -4`)*
- Or use `tailscale serve`:
  ```bash
  tailscale serve --bg 8000
  ```

Access the dashboard on any device in your Tailscale network:
```
http://<your-machine-tailscale-name>:8000
```

---

## 3. Public Demo Deployment (Cloudflare Pages)

If deploying a public showcase or demonstration of the FirstShot dashboard, follow these strict separation rules:

> [!CAUTION]
> NEVER deploy your authenticated college session cookies or private database to a public cloud service. The public demo must use **Simulated Provider** mode only.

### Deployment Steps:

1. **Build Frontend**:
   ```bash
   cd frontend
   npm run build
   ```
2. **Deploy to Cloudflare Pages**:
   - In Cloudflare Dashboard, navigate to **Workers & Pages** > **Create application** > **Pages**.
   - Connect your GitHub repository.
   - Build configuration:
     - **Framework preset**: Vite
     - **Build command**: `npm run build`
     - **Build output directory**: `dist`
     - **Root directory**: `frontend`
3. **SPA Routing**:
   The `frontend/public/_redirects` file is included in the build output to handle client-side routing on Cloudflare Pages.
