## NETWORK SECURITY ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    NETWORK SECURITY GROUPS (NSG)                             │
└─────────────────────────────────────────────────────────────────────────────┘

INTERNET ────────────────────────────────────────────────────────────────────
    │
    │ HTTPS (443)
    ▼
┌─────────────────────────────────────────────────┐
│              AZURE FIREWALL                      │
│  Rules:                                          │
│  - Allow 443 to SPM Public Container            │
│  - Allow 443 to USN/DSA/NVD sources             │
│  - Log all traffic                              │
└─────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────┐
│           NSG-PUBLIC-CONTAINER                   │
│  Inbound:                                        │
│  - 443 from Internet (Logic Apps)               │
│  - 5000 from Internal VNET                      │
│  Outbound:                                       │
│  - 443 to Internet (USN, DSA, NVD)              │
│  - 5432 to PostgreSQL                           │
└─────────────────────────────────────────────────┘
    │
    │ Private Endpoint (5432)
    ▼
┌─────────────────────────────────────────────────┐
│              NSG-DATA                            │
│  Inbound:                                        │
│  - 5432 from Public Container                   │
│  - 5432 from Internal Container                 │
│  - 5432 from UYUNI Server                       │
│  Outbound:                                       │
│  - DENY ALL                                     │
└─────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────┐
│           NSG-MASTER                             │
│  Inbound:                                        │
│  - 443, 5000 from Proxy Servers                 │
│  - 22 from Azure Bastion                        │
│  Outbound:                                       │
│  - 443 to Internet (SUSE repos)                 │
│  - 5432 to PostgreSQL                           │
│  - 4505, 4506 to Proxy                          │
└─────────────────────────────────────────────────┘
    │
    │ VNet Peering
    ▼
┌─────────────────────────────────────────────────┐
│              NSG-PROXY                           │
│  Inbound:                                        │
│  - 443 from Master                              │
│  - 4505, 4506 from Master (Salt)               │
│  - 22 from Bastion                              │
│  Outbound:                                       │
│  - 22, 4505, 4506 to Client VMs                │
│  - 443 to Master                                │
└─────────────────────────────────────────────────┘
    │
    ├─────────────────┬─────────────────┐
    │                 │                 │
    ▼                 ▼                 ▼
┌───────────┐  ┌───────────┐  ┌─────────────────────┐
│NSG-CLIENT │  │NSG-CLIENT │  │     NSG-TEST        │
│  Inbound: │  │ VM 2      │  │  Inbound:           │
│  - 22 from│  │           │  │  - 22 from Proxy    │
│    Proxy  │  │           │  │  Outbound:          │
│  Outbound:│  │           │  │  - DENY ALL         │
│  - 80,443 │  │           │  │  (Completely        │
│    to Repo│  │           │  │   Isolated)         │
└───────────┘  └───────────┘  └─────────────────────┘
```

## SCHEDULING TIMELINE

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DAILY SCHEDULING TIMELINE                                 │
└─────────────────────────────────────────────────────────────────────────────┘

00:00 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  │
  ├─ 00:30  ┌─────────────────────────────────────┐
  │         │ CRON: errata-push.sh                │
  │         │ Push pending errata to UYUNI        │
  │         └─────────────────────────────────────┘
  │
  ├─ 01:00  ┌─────────────────────────────────────┐
  │         │ CRON: sync-channels.sh              │
  │         │ Sync UYUNI channels from repos      │
  │         └─────────────────────────────────────┘
  │
  ├─ 02:00  ┌─────────────────────────────────────┐  (Solo Domenica)
  │         │ LOGIC APP: logic-oval-sync          │
  │         │ POST /api/sync/oval?platform=all    │
  │         │ Timeout: 60 min                     │
  │         └─────────────────────────────────────┘
  │
  ├─ 03:00  ┌─────────────────────────────────────┐
  │         │ LOGIC APP: logic-dsa-sync           │
  │         │ POST /api/sync/dsa/full             │
  │         │ Timeout: 30 min                     │
  │         └─────────────────────────────────────┘
  │
  ├─ 04:00  ┌─────────────────────────────────────┐
  │         │ LOGIC APP: logic-nvd-sync           │
  │         │ POST /api/sync/nvd?batch_size=200   │
  │         │ Timeout: 30 min                     │
  │         └─────────────────────────────────────┘
  │
06:00 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  │
  ├─ 06:00  ┌─────────────────────────────────────┐
  │         │ LOGIC APP: logic-usn-sync           │
  │         │ POST /api/sync/usn                  │
  │         └─────────────────────────────────────┘
  │
  ├─ 06:30  ┌─────────────────────────────────────┐
  │         │ CRON: errata-push.sh                │
  │         └─────────────────────────────────────┘
  │
12:00 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  │
  ├─ 12:00  ┌─────────────────────────────────────┐
  │         │ LOGIC APP: logic-usn-sync           │
  │         └─────────────────────────────────────┘
  │
  ├─ 12:30  ┌─────────────────────────────────────┐
  │         │ CRON: errata-push.sh                │
  │         └─────────────────────────────────────┘
  │
18:00 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  │
  ├─ 18:00  ┌─────────────────────────────────────┐
  │         │ LOGIC APP: logic-usn-sync           │
  │         └─────────────────────────────────────┘
  │
  ├─ 18:30  ┌─────────────────────────────────────┐
  │         │ CRON: errata-push.sh                │
  │         └─────────────────────────────────────┘
  │
24:00 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

LEGEND:
━━━━━━━  Timeline
┌─────┐  Scheduled Job
CRON     Server-side cron job
LOGIC    Azure Logic App trigger
```

---

## TECHNOLOGY STACK SUMMARY

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         TECHNOLOGY STACK                                     │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────┬────────────────────────────────────────────────────────────┐
│    LAYER        │                      COMPONENTS                            │
├─────────────────┼────────────────────────────────────────────────────────────┤
│                 │  Azure Logic Apps (Scheduling)                             │
│  ORCHESTRATION  │  Azure Container Instances (SPM API)                       │
│                 │  Cron Jobs (UYUNI Server)                                  │
├─────────────────┼────────────────────────────────────────────────────────────┤
│                 │  Flask 3.0 + Gunicorn (REST API)                          │
│  APPLICATION    │  UYUNI 2024.05 (Patch Management)                         │
│                 │  n8n (Workflow Automation)                                 │
│                 │  Groq AI (LLM for Service Remediation)                    │
├─────────────────┼────────────────────────────────────────────────────────────┤
│                 │  Salt (Configuration Management)                           │
│  CONFIG MGMT    │  Salt Master (UYUNI integrated)                           │
│                 │  Salt Minion (Client agents)                              │
├─────────────────┼────────────────────────────────────────────────────────────┤
│                 │  PostgreSQL 14 (Azure Flexible Server)                    │
│  DATABASE       │  PostgreSQL (UYUNI internal)                              │
├─────────────────┼────────────────────────────────────────────────────────────┤
│                 │  Podman (UYUNI containerized)                             │
│  CONTAINERS     │  Docker (n8n, SPM API local dev)                          │
│                 │  Azure Container Instances (Production)                    │
├─────────────────┼────────────────────────────────────────────────────────────┤
│                 │  Azure Virtual Network (Hub-Spoke)                        │
│  NETWORK        │  Azure Firewall Premium                                    │
│                 │  Network Security Groups                                   │
│                 │  Private Endpoints                                         │
├─────────────────┼────────────────────────────────────────────────────────────┤
│                 │  Azure Key Vault (Secrets)                                │
│  SECURITY       │  Azure Bastion (Secure Access)                            │
│                 │  Microsoft Defender for Cloud                             │
│                 │  Microsoft Sentinel (SIEM)                                │
├─────────────────┼────────────────────────────────────────────────────────────┤
│                 │  Azure Storage Account (Blobs)                            │
│  STORAGE        │  Azure Managed Disks (VM)                                 │
│                 │  Azure Snapshots (P3 Testing)                             │
├─────────────────┼────────────────────────────────────────────────────────────┤
│                 │  Log Analytics Workspace                                   │
│  MONITORING     │  Azure Monitor                                             │
│                 │  Application Insights                                      │
└─────────────────┴────────────────────────────────────────────────────────────┘

SUPPORTED CLIENT OS:
┌────────────────────────┬─────────┬─────────┐
│ Operating System       │ x86-64  │ aarch64 │
├────────────────────────┼─────────┼─────────┤
│ Ubuntu 24.04/22.04     │   ✓     │    -    │
│ Debian 12              │   ✓     │    -    │
│ RHEL 9/8               │   ✓     │   ✓     │
│ AlmaLinux 9/8          │   ✓     │   ✓     │
│ Rocky Linux 9/8        │   ✓     │   ✓     │
│ Oracle Linux 9/8/7     │   ✓     │   ✓     │
│ SUSE Linux Enterprise  │   ✓     │   ✓     │
└────────────────────────┴─────────┴─────────┘
```
