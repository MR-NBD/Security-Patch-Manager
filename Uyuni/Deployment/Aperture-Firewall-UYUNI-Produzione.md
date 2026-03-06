# Aperture Firewall — UYUNI Produzione

VM: `uyuni-master-01` — IP: `198.18.23.4`

---

## Outbound — VM → Internet (Azure Firewall Application Rules)

| FQDN | Porta | Motivo |
|---|---|---|
| `download.opensuse.org` | 80, 443 | zypper — pacchetti OS e repo UYUNI |
| `registry.opensuse.org` | 443 | Podman — pull immagini container UYUNI |

---

## Outbound — VM → Rete interna

| Destinazione | Porta | Motivo |
|---|---|---|
| `10.65.10.2` | TBD | Proxy HTTP interno (da verificare) |

---

## Inbound — Client → UYUNI Server (NSG)

| Porta | Source | Motivo |
|---|---|---|
| 443 | 10.172.2.0/24 | Web UI + client |
| 4505-4506 | 10.172.2.0/24 | Salt Master |
| 22 | IP Azure Bastion | SSH amministrazione |
