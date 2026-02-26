# UYUNI Proxy in Cascata

Guida alle **sole differenze** rispetto all'installazione di un proxy singolo.
Prerequisito: seguire integralmente `Installazione-UYUNI-Proxy.md` con le eccezioni indicate qui sotto.

---

## Architettura

```
Client
  → Proxy-Due  (10.172.2.23)   ← nuovo
      → Proxy-Uno  (10.172.2.20)   ← parent
          → Server UYUNI  (10.172.2.17)
```

---

## Differenze rispetto a un proxy singolo

### 1. NSG — regole outbound

Il proxy in cascata **non parla direttamente con il server**. Le regole outbound puntano al proxy parent, non a `10.172.2.17`.

| Destinazione | Porte | Motivo |
|---|---|---|
| `10.172.2.20` (proxy-uno) | TCP 443 | Squid → cache upstream |
| `10.172.2.20` (proxy-uno) | TCP 4505-4506 | Salt broker upstream |

Nessuna regola outbound verso `10.172.2.17`.

---

### 2. Salt minion — master

Il minion del proxy in cascata deve puntare al **proxy parent**, non al server.

File: `/etc/salt/minion.d/uyuni.conf`

```
# Proxy singolo (standard)
master: uyuni-server-test.uyuni.internal

# Proxy in cascata ← DIFFERENZA
master: uyuni-proxy-test.uyuni.internal
```

Dopo la modifica:
```bash
sudo systemctl restart salt-minion
# Verifica: deve mostrare 10.172.2.20, non 10.172.2.17
ss -tnp | grep ESTAB | grep -E '4505|4506'
```

---

### 3. Generazione config.tar.gz — parent proxy

Il secondo argomento di `proxy_container_config_generate_cert` è il **parent**.
Per un proxy in cascata il parent è il proxy-uno, non il server.

```bash
# Proxy singolo (standard)
mgrctl exec -ti 'spacecmd proxy_container_config_generate_cert -- \
  uyuni-proxy-test.uyuni.internal \
  uyuni-server-test.uyuni.internal \      ← parent = server
  38000 admin@example.com -o /tmp/config.tar.gz -p 8022'

# Proxy in cascata ← DIFFERENZA
mgrctl exec -ti 'spacecmd proxy_container_config_generate_cert -- \
  uyuni-proxy-due-test.uyuni.internal \
  uyuni-proxy-test.uyuni.internal \       ← parent = proxy-uno
  38000 admin@example.com -o /tmp/config.tar.gz -p 8022'
```

---

### 4. Installazione container

Identica al proxy singolo, con il tar.gz generato al punto precedente:

```bash
sudo mgrpxy install podman /tmp/proxy-due-cascade-config.tar.gz
```

---

## Verifica cascata

Dopo l'installazione, controlla che Apache di proxy-due punti a proxy-uno:

```bash
podman exec uyuni-proxy-httpd cat /etc/apache2/conf.d/smlm-proxy-forwards.conf | grep ProxyPass
```

Il risultato atteso mostra `uyuni-proxy-test.uyuni.internal` come destinazione di tutti i `ProxyPass`, **non** il server UYUNI.

Conferma connessione Salt:
```bash
ss -tnp | grep ESTAB | grep -E '4505|4506'
# ESTAB ... 10.172.2.23 → 10.172.2.20:4505  ← corretto
```

---

## Trasferimento config.tar.gz (Azure Bastion — no SCP)

Genera sul server, servi via `/pub/`, scarica sul proxy:

```bash
# Sul server UYUNI (10.172.2.17)
mgrctl cp server:/tmp/proxy-due-cascade-config.tar.gz /tmp/
cp /tmp/proxy-due-cascade-config.tar.gz \
  $(podman volume inspect srv-www | grep Mountpoint | awk -F'"' '{print $4}')/htdocs/pub/

# Sul proxy-due (10.172.2.23)
curl -k -o /tmp/proxy-due-cascade-config.tar.gz \
  https://uyuni-server-test.uyuni.internal/pub/proxy-due-cascade-config.tar.gz
```
