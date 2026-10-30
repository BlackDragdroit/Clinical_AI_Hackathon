#!/usr/bin/env bash
# Replay a scenario case against the running stack (make up), end to end, in a few seconds. Owner: SWE 1.
#   scripts/dev/flow.sh r1   request 1: lab by email, Dr. Brandl answers           -> filed
#   scripts/dev/flow.sh r2   request 2: rehab report by SMS, Stefan Kern answers   -> filed
#   scripts/dev/flow.sh m1   wrong address (labor-kanaI), a stranger opens it      -> blocked, nothing shown
#   scripts/dev/flow.sh m2   forwarded to Karl Kollege                             -> blocked, nothing shown
#   scripts/dev/flow.sh m3   Dr. Brandl uploads Max Beispiel's result               -> not filed
# Prints the outcome the outside person sees, the audit events and Dr. Hofer's last Matrix message.
set -uo pipefail
cd "$(dirname "$0")/../.."
MX=scripts/dev/mx.sh
R1='!anfrage labor "Dr. Eva Brandl" eva.brandl@labor-kanal.example Patient/maria-beispiel Grund: Gerinnung vor Eingriff'
R2='!anfrage bericht "Stefan Kern" +436600000101 Patient/maria-beispiel Grund: Entlassungsbericht'
LAB=scenario/documents/lab-result-maria-beispiel.md; MAX=scenario/documents/lab-result-max-beispiel.md
REHAB=scenario/documents/rehab-report-maria-beispiel.md
case "${1:-}" in
  r1) cmd=$R1; who=eva; doc=$LAB; tn="Maria Beispiel"; td=12.03.1961 ;;
  r2) cmd=$R2; who=stefan; doc=$REHAB; tn="Maria Beispiel"; td=12.03.1961 ;;
  m1) cmd=${R1/labor-kanal.example/labor-kanaI.example}; who=unbekannt; doc=$LAB; tn="Maria Beispiel"; td=12.03.1961 ;;
  m2) cmd=$R1; who=karl; doc=$LAB; tn="Maria Beispiel"; td=12.03.1961 ;;
  m3) cmd=$R1; who=eva; doc=$MAX; tn="Max Beispiel"; td=01.01.1960 ;;
  *) sed -n 2,9p "$0"; exit 2 ;;
esac
# the card is followed by its "Senden" reaction (not a message), so read a few events and take the newest card
id=$(N=6 $MX "$cmd" | grep -oE 'Anfrage [a-z0-9]{8}' | tail -1 | cut -d' ' -f2)
[ -n "$id" ] || { echo "no draft card from the bot (is the stack up? see: docker compose logs app)"; exit 1; }
N=1 $MX "!senden $id" >/dev/null
if [ "$1" = r2 ]; then
  link=$(curl -s localhost:8000/sms | grep -oE 'http://[^"<]+/r/[A-Za-z0-9_-]+' | head -1)
else
  mid=$(curl -s "localhost:8025/api/v1/messages?limit=1" | python3 -c 'import json,sys;print(json.load(sys.stdin)["messages"][0]["ID"])')
  link=$(curl -s "localhost:8025/api/v1/message/$mid" | python3 -c 'import json,sys,re;print(re.search(r"http://\S+/r/\S+", json.load(sys.stdin)["Text"]).group(0))')
fi
path=${link#http://*/}; url="http://localhost:8000/$path"
jar=$(mktemp); trap 'rm -f "$jar"' EXIT
curl -s -c "$jar" -b "$jar" "$url" >/dev/null
page=$(curl -s -c "$jar" -b "$jar" -L -w '\n%{http_code}' localhost:8000/eid/authorize -d "state=${path##*/}&citizen=$who")
echo "request $id  after ID Austria: HTTP $(tail -1 <<<"$page")  $(grep -oE '<h2>[^<]*</h2>' <<<"$page" | head -1 | sed 's/<[^>]*>//g')"
if grep -q "Sicher senden" <<<"$page"; then
  curl -s -c "$jar" -b "$jar" "$url/answer" -F typed_name="$tn" -F typed_dob="$td" -F "upload=@$doc;type=text/markdown" \
    | grep -oE '<p>[^<]*</p>' | head -1 | sed 's/<[^>]*>//g; s/^/sender sees: /'
fi
sleep 3
curl -s "localhost:8000/audit.json?request_id=$id" | python3 -c 'import json,sys
a=json.load(sys.stdin); print("audit:", ", ".join(e["event"] + ("(" + (e["details"].get("result") or e["details"].get("type") or "") + ")" if (e["details"].get("result") or e["details"].get("type")) else "") for e in a["entries"]))'
WAIT=0 N=6 $MX | grep -v '^@lena' | tail -3 | cut -c1-220
