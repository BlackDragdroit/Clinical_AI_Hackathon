# Remote test from one PC

The whole demo from your PC through one public HTTPS address, so teammates (or the jury) test in their browser
with nothing installed. Synthetic data only.

```bash
make up                               # the stack, as usual
ngrok http 8088                       # another terminal (or any tunnel to localhost:8088)
make public URL=https://<ngrok-host>  # = scripts/public_up.sh https://<ngrok-host>
```

Then share `https://<ngrok-host>`:

| Path | What |
|---|---|
| `/` | Element, Dr. Hofer's chat (log in as `lena.hofer`, password from `.env`; send it separately) |
| `/mailpit/` | the e-mails with the portal links, for playing the lab |
| `/r/…`, `/eid/…` | the portal the outside person uses |
| `/audit`, `/befund/…`, `/dashboard` | audit trail, report page, dashboard widget |
| `/fhir/…` | the patient record, **read-only** (GET only) |

Not reachable from outside: the AI engine, the models and the GPU tunnel, Synapse's admin API, HAPI writes.

Back to localhost: `make public URL=--off`. While public, Mailpit lives under `/mailpit/`, so
`scripts/dev/flow.sh` and `make metrics` (which use `localhost:8025/api/v1`) need `--off` first.

## How it works
- `nginx.conf`: one entry on `:8088`. `/_matrix` → Synapse, the app's paths → app, `/mailpit/` → Mailpit,
  `/fhir/` → HAPI with GET only, everything else → Element. Element gets `element-public.json` (written by the
  script, with the public address as homeserver) as its host-specific config.
- `ngrok-fix.js`: ngrok's free plan answers browser requests that carry neither its cookie nor the header
  `ngrok-skip-browser-warning` with a warning page. Element's API calls carry no cookie, so the router adds this
  small script to Element's page; it puts the header on every same-origin request. Element's page is always sent
  in full (`no-store`), so a cached copy without the script cannot linger. Not needed with other tunnels; harmless.
- The address changes when ngrok restarts: run `make public URL=…` again with the new one.
