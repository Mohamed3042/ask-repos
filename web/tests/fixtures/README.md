# Recorded API responses

`ask-response.json` is a real `POST /v1/ask` response, captured from the running service
with the extractive (keyless) provider:

```bash
curl -s -X POST http://localhost:8080/v1/ask \
  -H 'content-type: application/json' \
  -d '{"question":"Which Kuwait branches does the Retail Ops Hub demo cover?","k":8,"provider":"extractive"}' \
  -o web/tests/fixtures/ask-response.json
```

It exists so `lib/citations.test.ts` can assert that the URL the citation chip builds is
byte-identical to the URL the API produced — for a real citation, not an invented one.
Re-record it whenever the citation format changes; the test is meant to go red first.
