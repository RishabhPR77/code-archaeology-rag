# Code Archaeologist on Azure (a second copy, next to Render)

This runs a second, always-on copy of the site on the Azure VM that already hosts Tejaskrit. It costs
nothing extra: it uses the VM that's already running, a free address and free container hosting on GitHub.

**What stays exactly as it is**

- **Render.** Its service, settings, database and auto-deploys are untouched. It keeps working as before, and
  it comes back on its own when Render's free hours reset.
- **Tejaskrit.** Its code, containers, database and Compose file are untouched. The only shared piece is
  Caddy, the HTTPS front door on ports 80/443, which gets one *added* site block (step 5). Caddy checks a config
  before applying it and reloads without downtime, so Tejaskrit never goes down, even if the new block had a
  mistake.
- **Fair share of the VM.** The copy is its own Compose project. Its app is capped at 512 MB of memory and one
  CPU, its database at 192 MB and half a CPU, it runs one ingest at a time, and nothing publishes a port. If it
  ever needs more, only it restarts.

**How the copy is wired**

```
visitor ──HTTPS──> Caddy (Tejaskrit's) ──> codearch app ──> its own PostgreSQL (on the VM) + Pinecone + GitHub
                         └──────────────> Tejaskrit (unchanged)
```

The copy has its own PostgreSQL container on the VM, filled with a copy of Render's database in step 3. Being
on the same machine, every query is local, and Render's database is only read once, for the copy.

---

## Steps

### 1. An address

`codearch.20-2-69-168.sslip.io` works straight away: sslip.io is a free service that points any name ending in
`20-2-69-168.sslip.io` to the VM's IP, with no sign-up, and Caddy gets an HTTPS certificate for it. For a nicer
name later, point a domain of your own (or a free DuckDNS name) at `20.2.69.168`, and replace the name in
`codearch.env` and the Caddyfile.

### 2. Set up the folder (on the VM)

```bash
ssh -i ~/.ssh/tejaskrit_key.pem azureuser@20.2.69.168
curl -fsSL https://raw.githubusercontent.com/RishabhPR77/code-archaeology-rag/main/deploy/azure/setup.sh \
  | bash -s -- codearch.20-2-69-168.sslip.io
```

This creates `~/codearch` with the Compose file and scripts, generates the new database's password on the
VM, and writes `codearch.env` with every setting that isn't a secret already filled in.

### 3. Paste the secrets, copy the database

```bash
cd ~/codearch && nano codearch.env move-database.env     # Ctrl+O saves, Ctrl+X goes to the next file
```

Copy each empty value from Render → code-archaeologist → **Environment**. `SECRET_KEY` and `ENCRYPTION_KEY`
must be **exactly the same as on Render**: the copied database holds API keys encrypted with them. In
`move-database.env`, paste Render's `DATABASE_URL`.

```bash
sudo ./move-database.sh      # prints row counts, old -> new; they should match
rm move-database.env
```

### 4. Start it

The image comes from GitHub's container registry. It's published by the "Container image" workflow after CI
passes, and the package has to be **public** (GitHub → your profile → Packages → `code-archaeology-rag` →
Package settings → Change visibility). The code is public already, so this reveals nothing new.

```bash
sudo docker compose pull && sudo docker compose up -d
sudo docker compose ps        # both should become "healthy"
```

### 5. Add the site to Caddy (Tejaskrit keeps running throughout)

```bash
cd ~/app/deploy/azure
cp Caddyfile Caddyfile.before-codearch          # a backup, for undo
sed "s/codearch.example.duckdns.org/codearch.20-2-69-168.sslip.io/" ~/codearch/Caddyfile.site >> Caddyfile
sudo docker exec azure-caddy-1 caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
sudo docker exec azure-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

`validate` must say "Valid configuration" before you run `reload`. If it doesn't, run
`cp Caddyfile.before-codearch Caddyfile`: nothing was applied, and Tejaskrit never noticed. That Caddyfile is
part of Tejaskrit's repository, so commit the added block there too, or a future Tejaskrit deploy would drop it.

### 6. Allow sign-in from the new address (keep Render's entries)

- **GitHub App** (github.com → Settings → Developer settings → GitHub Apps → your app): under **Callback URL**,
  *add* `https://codearch.20-2-69-168.sslip.io/api/auth/github/callback`.
- **Google** (console.cloud.google.com → APIs & Services → Credentials → your OAuth client): *add* the redirect
  URI `https://codearch.20-2-69-168.sslip.io/api/auth/google/callback` and the JavaScript origin
  `https://codearch.20-2-69-168.sslip.io`.
- **Brevo**, only if you turned on **Authorized IPs**: add `20.2.69.168`.

### 7. Check it

- `https://codearch.20-2-69-168.sslip.io` loads, and **Try the live demo** works.
- Sign in, and open **Settings → Security activity**: your network should be shown.
- A faked IP must not get around the rate limit. From your own computer, this should print ten `200`s, then `429`:

  ```bash
  for i in $(seq 1 11); do curl -s -o /dev/null -w "%{http_code} " -X POST -H "X-Real-IP: 203.0.113.$i" -H "X-Forwarded-For: 198.51.100.$i" https://codearch.20-2-69-168.sslip.io/api/auth/demo; done; echo
  ```

---

## Day to day

- **Updating:** push to `main` as usual. Render deploys by itself, as before. For Azure, wait for the
  "Container image" workflow (a few minutes after CI), then run `sudo ~/codearch/update.sh` on the VM. It only
  restarts Code Archaeologist.
- **Two independent copies:** from the move on, each has its own accounts and data. Repositories that existed at
  the move share their search vectors with Render's copy, so delete or re-sync those on one side only. Anything
  added later is separate.
- **Backups:** the data is in the `codearch_pgdata` volume on the VM's disk. For a copy:
  `sudo docker exec codearch-db-1 pg_dump -U codearch codearch | gzip > ~/codearch-$(date +%F).sql.gz`
- **Watching it:** `sudo docker compose ps` (should say "healthy") and `sudo docker stats --no-stream`.

## Undo

```bash
cd ~/app/deploy/azure && cp Caddyfile.before-codearch Caddyfile
sudo docker exec azure-caddy-1 caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
cd ~/codearch && sudo docker compose down        # add -v to delete this copy's database too
```

Tejaskrit and Render are unaffected either way.
