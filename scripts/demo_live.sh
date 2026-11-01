#!/usr/bin/env bash
set -euo pipefail

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TMP_FILE="$(mktemp /tmp/lkb-demo.XXXXXX.md)"
trap 'rm -f "$TMP_FILE"' EXIT

printf '# Live Demo Document\n\nThis is a temporary document.\n' > "$TMP_FILE"

echo "== health =="
curl -fsS "$BASE_URL/health"
echo

echo "== openapi info =="
curl -fsS "$BASE_URL/openapi.json" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["info"]["title"], d["openapi"])'

echo "== upload document =="
UPLOAD_RESPONSE="$(curl -fsS -F "file=@$TMP_FILE;type=text/markdown" "$BASE_URL/documents")"
echo "$UPLOAD_RESPONSE"

DOCUMENT_ID="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])' <<<"$UPLOAD_RESPONSE")"

echo "== document detail =="
curl -fsS "$BASE_URL/documents/$DOCUMENT_ID"
echo

echo "== chat =="
curl -fsS -X POST "$BASE_URL/chat" \
  -H 'Content-Type: application/json' \
  -d '{"question":"什么是 RAG？"}'
echo

echo "== delete document =="
curl -fsS -X DELETE "$BASE_URL/documents/$DOCUMENT_ID"
echo
