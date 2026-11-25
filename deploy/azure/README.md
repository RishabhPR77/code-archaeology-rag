# Code Archaeologist on Azure (a second copy, next to Render)

This runs a second, always-on copy of the site on the Azure VM that already hosts Tejaskrit.

**What stays exactly as it is**

- **Render.** Its service, settings, database and auto-deploys are untouched. It keeps working as before, and
  it comes back on its own when Render's free hours reset.
- **Tejaskrit.** Its code, container, database and Compose file are untouched. The only shared piece is Caddy,
  the HTTPS front door on ports 80/443, which gets one *added* site block (step 5). Caddy checks a config
  before applying it and reloads without downtime, so Tejaskrit never goes down, even if the new block had a
  mistake.
- **Fair share of the VM.** Code Archaeologist is capped at 512 MB of memory (plus 512 MB of swap) and one of
  the two CPUs, runs one ingest at a time, and publishes no ports. If it ever needs more, only it restarts.

**How the copy is wired**

```
visitor ──HTTPS──> Caddy (Tejaskrit's) ──> codearch container ──> Neon (Singapore copy) + Pinecone + GitHub
                         └──────────────> Tejaskrit (unchanged)
```

The Azure copy gets its own database, copied from Render's in step 4, in Neon's Singapore region: the VM is in
East Asia, and Render's database is in US East, about 0.2 s away per query.

---

## Steps

Steps marked 🙋 need your accounts. Everything else is copy and paste.

### 1. 🙋 A domain for this copy

Tejaskrit's address belongs to Tejaskrit, so this copy needs its own. The quickest free option:

1. Sign in at [duckdns.org](https://www.duckdns.org) with GitHub or Google.
2. Add a subdomain, for example `codearch-rishabh`, and set its **current ip** to `20.2.69.168` (the VM).

Your domain is then `codearch-rishabh.duckdns.org`. Use it everywhere below in place of `YOUR_DOMAIN`.
(A domain of your own works the same way: add an A record pointing to `20.2.69.168`.)

### 2. 🙋 A database in Singapore

1. In the [Neon console](https://console.neon.tech), open the current project and note its **Postgres version**.
2. Create a **new project**: region **AWS Asia Pacific (Singapore)**, the same Postgres version.
3. Copy its connection string (the **direct** one, without `-pooler` in the host).

Render's project is not changed.

### 3. 🙋 Make the image public (once)

After this folder is pushed, GitHub Actions publishes the app's image when CI passes ("Container image"
workflow). Then: GitHub → your profile → **Packages** → `code-archaeology-rag` → **Package settings** →
**Change visibility** → **Public**. The code is already public, so this reveals nothing new, and the VM can
download the image without a password.

### 4. On the VM: settings and the database copy

Sign in to the VM (`ssh azureuser@20.2.69.168`), then:

```bash
mkdir -p ~/codearch && cd ~/codearch
for f in docker-compose.yml update.sh move-database.sh codearch.env.example; do
  curl -fsSLO "https://raw.githubusercontent.com/RishabhPR77/code-archaeology-rag/main/deploy/azure/$f"
done
chmod +x update.sh move-database.sh
cp codearch.env.example codearch.env && chmod 600 codearch.env
nano codearch.env      # fill it in: copy values from Render → code-archaeologist → Environment
```

`SECRET_KEY` and `ENCRYPTION_KEY` must be **the same as on Render**: the copied database holds API keys
encrypted with them. `DATABASE_URL` is the **new** Singapore string, and `FRONTEND_URL` is `https://YOUR_DOMAIN`.

Copy the database. This only *reads* Render's database:

```bash
nano move-database.env   # two lines: OLD_DATABASE_URL=<Render's> and NEW_DATABASE_URL=<Singapore>
./move-database.sh       # prints row counts old -> new; they should match
rm move-database.env
```

Start the app:

```bash
docker compose pull && docker compose up -d
docker compose logs --tail 30     # look for "Application startup complete"
```

### 5. Add the site to Caddy (Tejaskrit keeps running throughout)

```bash
cd ~/app/deploy/azure
cp Caddyfile Caddyfile.before-codearch          # a backup, for undo
curl -fsSL https://raw.githubusercontent.com/RishabhPR77/code-archaeology-rag/main/deploy/azure/Caddyfile.site \
  | sed "s/codearch.example.duckdns.org/YOUR_DOMAIN/" >> Caddyfile
docker exec azure-caddy-1 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker exec azure-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

`validate` must say "Valid configuration" before you run `reload`. If it doesn't, run
`cp Caddyfile.before-codearch Caddyfile`: nothing was applied, and Tejaskrit never noticed.

That Caddyfile is part of Tejaskrit's repository. Commit the added block there too, so a future Tejaskrit
deploy doesn't drop it.

### 6. 🙋 Allow sign-in from the new address (keep Render's entries)

- **GitHub App** (github.com → Settings → Developer settings → GitHub Apps → your app): under
  **Callback URL**, *add* `https://YOUR_DOMAIN/api/auth/github/callback`.
- **Google** (console.cloud.google.com → APIs & Services → Credentials → your OAuth client): *add* the
  redirect URI `https://YOUR_DOMAIN/api/auth/google/callback` and the JavaScript origin `https://YOUR_DOMAIN`.
- **Brevo**, only if you turned on **Authorized IPs**: add `20.2.69.168`.

### 7. Check it

- `https://YOUR_DOMAIN` loads, and **Try the live demo** works.
- Sign in, ask a question, and open **Settings → Security activity**: your network should be shown.
- From your own computer, a faked IP must not get around the rate limit. This should print ten `200`s, then `429`:

  ```bash
  for i in $(seq 1 11); do curl -s -o /dev/null -w "%{http_code} " -X POST -H "X-Real-IP: 203.0.113.$i" -H "X-Forwarded-For: 198.51.100.$i" https://YOUR_DOMAIN/api/auth/demo; done; echo
  ```

---

## Day to day

- **Updating:** push to `main` as usual. Render deploys by itself, as before. For Azure, wait for the
  "Container image" workflow (a few minutes after CI), then run `~/codearch/update.sh` on the VM. It only
  restarts Code Archaeologist.
- **Two independent copies:** from the move on, each has its own accounts and data. Repositories that existed
  at the move share their search vectors with Render's copy, so delete or re-sync those on one side only.
  Anything added later is separate.
- **Watching it:** `docker compose ps` (should say "healthy") and `docker stats --no-stream` (memory stays under the cap).

## Undo

```bash
cd ~/app/deploy/azure && cp Caddyfile.before-codearch Caddyfile
docker exec azure-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
cd ~/codearch && docker compose down
```

Tejaskrit and Render are unaffected either way.
