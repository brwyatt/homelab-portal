# Homelab Portal

A lightweight, secure, and fast homelab landing page and service dashboard built with FastAPI, Jinja2, and vanilla JavaScript.

Designed specifically for homelabs and internal infrastructures fronted by reverse proxies (such as Nginx, HAProxy, Authelia, and Cloudflare Tunnels), Homelab Portal automatically classifies users and network origins to present only the relevant and authorized services.

---

## Features

* **Dynamic Network Location Detection**:
  * Automatically classifies client connections using CIDRs and longest-prefix matching.
  * Walks `X-Forwarded-For` right-to-left past configured trusted reverse proxies, preventing IP spoofing.
  * Displays user-friendly network badges (e.g. `Management Network`, `Trusted LAN`, `Guest Wi-Fi`, or `WAN`).
* **Identity-Aware & Role-Based Access**:
  * Compatible with reverse-proxy authentication headers (e.g., Authelia, Authentik, FreeIPA).
  * Services can be restricted by network classes, user groups, or both.
* **Modern Themes**:
  * Ships with built-in themes:
    * `fiber-optic`: Deep navy and cyan neon accent theme matching modern tech homelabs.
    * `default`: Clean dark slate theme.
  * Supports custom external theme stylesheets loaded from `/etc/homelab-portal/themes/`.
* **Instant Client-Side Search**:
  * Fuzzy / substring search across service names, descriptions, and categories.
  * Keyboard navigation (`/` to search, `Esc` to clear).
* **Zero Client Dependencies**:
  * No heavy frontend frameworks or external CDN dependencies. Fully resilient to WAN outages.
* **Production Ready**:
  * Standard `/healthz` and `/readyz` probes.
  * Fully decoupled configuration via `/etc/homelab-portal/config.yml` or `PORTAL_CONFIG_PATH`.

---

## Configuration

The portal loads configuration using the following resolution order:
1. File path specified by the `PORTAL_CONFIG_PATH` environment variable.
2. `/etc/homelab-portal/config.yml`
3. `./config.yml` in the working directory.
4. `./config.yml.example` (default fallback).

See [`config.yml.example`](config.yml.example) for a complete reference.

### Network Classification Example

```yaml
network:
  trusted_proxies:
    - "127.0.0.1/32"
    - "::1/128"
    - "10.0.0.10/32"

network_classes:
  management:
    name: "Management Subnet"
    icon: "shield"
  internal:
    name: "Home LAN"
    icon: "house"
  external:
    name: "WAN / External"
    icon: "globe"

subnets:
  - cidr: "192.168.1.0/24"
    name: "Trusted LAN"
    network_class: "internal"
  - cidr: "10.10.0.0/24"
    name: "Server Management"
    network_class: "management"
```

### Service Definition Example

```yaml
services:
  - name: "Proxmox VE"
    url: "https://pve.example.com:8006"
    description: "Virtualization hypervisors"
    category: "core"
    requires_groups:
      - "admins"
    network_classes:
      - "management"
```

---

## Running Locally

```bash
# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run development server
uvicorn app.main:app --reload --port 8080
```

Open `http://localhost:8080` in your browser.

---

## Running Tests

```bash
pytest
```

---

## Deployment with systemd

An example systemd service unit is provided in [`systemd/homelab-portal.service.example`](systemd/homelab-portal.service.example).

```bash
sudo cp systemd/homelab-portal.service.example /etc/systemd/system/homelab-portal.service
sudo systemctl daemon-reload
sudo systemctl enable --now homelab-portal
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
