#!/usr/bin/env bash
# Share the running stack from this PC through one public HTTPS address (remote test with synthetic data only).
#   ngrok http 8088                                   # another terminal; any tunnel to localhost:8088 works
#   scripts/public_up.sh https://<tunnel-host>        # or: make public URL=https://<tunnel-host>
#   scripts/public_up.sh --off                        # back to localhost
# Points Element, the links in e-mails/SMS, the FHIR links and the dashboard widget at that address, starts the
# router (deploy/public: one entry for Element, Matrix, the app, /mailpit/ and read-only /fhir/) and restarts
# Mailpit under /mailpit/ and the app. The engine and the models stay unreachable from outside. See deploy/public/README.md.
set -euo pipefail
export MSYS_NO_PATHCONV=1 PYTHONIOENCODING=utf-8
cd "$(dirname "$0")/.."
PUB=${1:?usage: scripts/public_up.sh https://<public-host> | --off}
DC=(docker compose -f docker-compose.yml -f deploy/public/docker-compose.public.yml)
HS=http://localhost:8008

set_url() {   # BASE_URL HAPI_PUBLIC_URL
  grep -q '^HAPI_PUBLIC_URL=' .env || echo "HAPI_PUBLIC_URL=" >> .env
  sed -i "s|^BASE_URL=.*|BASE_URL=$1|; s|^HAPI_PUBLIC_URL=.*|HAPI_PUBLIC_URL=$2|" .env
}

widget() {    # the dashboard widget in the room points at the app's address
  set -a; source .env; set +a
  local tok room url
  tok=$(curl -fs -XPOST "$HS/_matrix/client/v3/login" -H 'Content-Type: application/json' \
    -d "{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"lena.hofer\"},\"password\":\"$DOCTOR_PASSWORD\"}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])')
  room=$(python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$MATRIX_ROOM_ID")
  url=$(docker compose exec -T app .venv/bin/python -m app.dashboard | tail -1)
  curl -fs -XPUT "$HS/_matrix/client/v3/rooms/$room/state/im.vector.modular.widgets/bb-dashboard" \
    -H "Authorization: Bearer $tok" -H 'Content-Type: application/json' \
    -d "$(python3 -c 'import json,sys; print(json.dumps({"type": "m.custom", "id": "bb-dashboard", "name": "IRIS Dashboard",
                                                         "url": sys.argv[1], "creatorUserId": sys.argv[2], "data": {}}))' "$url" "$DOCTOR_MXID")" >/dev/null
}

wait_app() { until curl -fs "$1" >/dev/null; do sleep 2; done; }   # redirect, not -o: no path translation here

if [ "$PUB" = "--off" ]; then
  set_url http://localhost:8000 http://localhost:8090/fhir
  "${DC[@]}" rm -sf public >/dev/null 2>&1 || true
  docker compose up -d --no-deps --force-recreate mailpit app     # Mailpit back on :8025 without /mailpit/
  wait_app localhost:8000/audit && widget
  echo "== back on localhost"
  exit 0
fi

PUB=${PUB%/}
python3 - "$PUB" <<'EOF'
import json, sys
from pathlib import Path
c = json.loads(Path("element/config.json").read_text(encoding="utf-8"))
c["default_server_config"]["m.homeserver"]["base_url"] = sys.argv[1]      # Element in a remote browser talks to this
Path("deploy/public/element-public.json").write_text(json.dumps(c, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
EOF
set_url "$PUB" "$PUB/fhir"
"${DC[@]}" up -d --no-deps --force-recreate mailpit app public
wait_app localhost:8088/audit && widget
echo "== public: $PUB   (Element /, Mailpit $PUB/mailpit/, audit $PUB/audit; ngrok: 'Visit Site' once)"
