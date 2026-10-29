#!/usr/bin/env bash
# Talk to the bot as Dr. Hofer without Element. Owner: SWE 1.
#   scripts/dev/mx.sh '!status ab12cd34'      send, wait $WAIT s (default 4), print the last $N (default 4) messages
#   scripts/dev/mx.sh                         only print the last messages
set -euo pipefail
cd "$(dirname "$0")/../.."
set -a; source .env; set +a
HS=http://localhost:8008
mkdir -p var; TOKF=var/.lena_token
login() {
  curl -fs -XPOST "$HS/_matrix/client/v3/login" -H 'Content-Type: application/json' \
    -d "{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"lena.hofer\"},\"password\":\"$DOCTOR_PASSWORD\"}" \
    | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])' > "$TOKF"
}
# a cached token dies with `make reset`; log in again when Synapse rejects it
[ -s "$TOKF" ] && curl -fs "$HS/_matrix/client/v3/account/whoami" -H "Authorization: Bearer $(cat "$TOKF")" >/dev/null || login
TOK=$(cat "$TOKF")
ROOM=$(python3 -c 'import sys,urllib.parse;print(urllib.parse.quote(sys.argv[1]))' "$MATRIX_ROOM_ID")
if [ -n "${1:-}" ]; then
  body=$(python3 -c 'import json,sys;print(json.dumps({"msgtype":"m.text","body":sys.argv[1]}))' "$1")
  curl -fs -XPUT "$HS/_matrix/client/v3/rooms/$ROOM/send/m.room.message/t$(date +%s%N)" -H "Authorization: Bearer $TOK" \
    -H 'Content-Type: application/json' -d "$body" >/dev/null
  sleep "${WAIT:-4}"
fi
curl -fs "$HS/_matrix/client/v3/rooms/$ROOM/messages?dir=b&limit=${N:-4}" -H "Authorization: Bearer $TOK" \
  | python3 -c 'import json,sys
for e in reversed(json.load(sys.stdin)["chunk"]):
    if e["type"]=="m.room.message": print(e["sender"].split(":")[0], "|", e["content"]["body"])'
