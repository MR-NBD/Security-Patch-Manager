**È il container API principale del sistema!** Non eliminarlo.

**Perché è lì e non in test_group:**

Il container deve stare nella VNet `ASL0603-spoke10-spoke-italynorth` per raggiungere:

- UYUNI server (10.172.2.5)
- PostgreSQL via Private Endpoint (10.172.2.6)

Se lo sposti in test_group, perde accesso alla rete privata e non funziona più.

**Riepilogo risorse:**

|Resource Group|Risorsa|Motivo|
|---|---|---|
|test_group|PostgreSQL, ACR|Risorse gestite centralmente|
|ASL0603-spoke10-rg-spoke-italynorth|aci-errata-api, Private Endpoint, subnet ACI|Devono stare nella VNet con UYUNI|