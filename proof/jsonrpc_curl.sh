#!/usr/bin/env bash
#
# Vendor-neutral A2A proof: discover the card, then send a message with a
# personal access token as the bearer, twice with the same contextId to prove
# the orchestrator reuses its Redis thread.
#
# Usage:
#   A2A_URL=https://a2a.vcec.cloud TOKEN=<personal-access-token> ./proof/jsonrpc_curl.sh
#
set -euo pipefail

A2A_URL="${A2A_URL:-http://localhost:9008}"
TOKEN="${TOKEN:?Set TOKEN to a Workoflow personal access token}"
CONTEXT_ID="${CONTEXT_ID:-proof-context-001}"
PROMPT="${PROMPT:-Who can help me with Kubernetes?}"

echo "== 1. Public discovery (no auth) =="
curl -fsS "${A2A_URL}/.well-known/agent-card.json" | sed -e 's/,/,\n/g' | head -40
echo

send_message() {
  local text="$1"
  curl -fsS -X POST "${A2A_URL}/" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "Content-Type: application/json" \
    -d @- <<JSON
{
  "jsonrpc": "2.0",
  "id": "1",
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "kind": "message",
      "messageId": "msg-$(date +%s%N)",
      "contextId": "${CONTEXT_ID}",
      "parts": [{"kind": "text", "text": ${text}}]
    }
  }
}
JSON
}

echo "== 2. message/send (turn 1, contextId=${CONTEXT_ID}) =="
send_message "$(printf '%s' "$PROMPT" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
echo
echo

echo "== 3. message/send (turn 2, same contextId -> reuses the Redis thread) =="
send_message "$(printf '%s' "And what about Terraform?" | python3 -c 'import json,sys; print(json.dumps(sys.stdin.read()))')"
echo
