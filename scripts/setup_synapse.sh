#!/usr/bin/env bash
# Synapse for klinikum.example: config, users @lena.hofer + @befundbruecke, one room, bot invited.
# Writes MATRIX_ROOM_ID into .env. Idempotent. Owner: SWE 1.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a
HS=http://localhost:8008
dc() { docker compose "$@"; }

if ! dc run --rm --entrypoint sh synapse -c 'test -f /data/homeserver.yaml'; then
  echo "== generating homeserver.yaml"
  dc run --rm synapse generate
  # demo/tests: the bot posts several messages quickly and test scripts log in often; lift those rate limits
  dc run --rm -T --entrypoint sh synapse -c '{ echo; cat; } >> /data/homeserver.yaml' <<'YAML'   # generated file has no trailing newline
rc_message:
  per_second: 50
  burst_count: 100
rc_login:
  address: {per_second: 10, burst_count: 50}
  account: {per_second: 10, burst_count: 50}
YAML
fi
dc up -d synapse
echo -n "== waiting for synapse"
until curl -fs "$HS/health" >/dev/null; do echo -n .; sleep 2; done; echo

reg() {  # user password
  dc exec -T synapse register_new_matrix_user -c /data/homeserver.yaml -u "$1" -p "$2" --no-admin http://localhost:8008 \
    2>&1 | grep -v "User ID already taken" || true
}
reg lena.hofer "$DOCTOR_PASSWORD"
reg befundbruecke "$MATRIX_BOT_PASSWORD"

login() {  # localpart password -> access token
  curl -fs -XPOST "$HS/_matrix/client/v3/login" -H 'Content-Type: application/json' \
    -d "{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"$1\"},\"password\":\"$2\"}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["access_token"])'
}
LENA=$(login lena.hofer "$DOCTOR_PASSWORD")
BOT=$(login befundbruecke "$MATRIX_BOT_PASSWORD")

urlq() { python3 -c 'import sys,urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$1"; }
# after `make reset` .env still names the room of the wiped homeserver: forget it so a new one is created
if [ -n "${MATRIX_ROOM_ID:-}" ] && ! curl -fs "$HS/_matrix/client/v3/rooms/$(urlq "$MATRIX_ROOM_ID")/joined_members" \
    -H "Authorization: Bearer $LENA" >/dev/null; then
  echo "== $MATRIX_ROOM_ID no longer exists"
  MATRIX_ROOM_ID=
fi
if [ -z "${MATRIX_ROOM_ID:-}" ]; then
  echo "== creating room"
  MATRIX_ROOM_ID=$(curl -fs -XPOST "$HS/_matrix/client/v3/createRoom" -H "Authorization: Bearer $LENA" \
    -H 'Content-Type: application/json' \
    -d "{\"name\":\"BefundBrücke – Anfragen\",\"preset\":\"private_chat\",\"invite\":[\"$MATRIX_BOT_USER\"]}" \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["room_id"])')
  sed -i "s|^MATRIX_ROOM_ID=.*|MATRIX_ROOM_ID=$MATRIX_ROOM_ID|" .env
fi
curl -fs -XPOST "$HS/_matrix/client/v3/join/$(urlq "$MATRIX_ROOM_ID")" \
  -H "Authorization: Bearer $BOT" -H 'Content-Type: application/json' -d '{}' >/dev/null
echo "== room $MATRIX_ROOM_ID ready (written to .env)"
