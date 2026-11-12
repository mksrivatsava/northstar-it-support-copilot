# Optional provider adapter checks

The default product makes no provider calls. Its optional Ollama adapter follows the non-streaming `POST /api/chat` contract documented at https://docs.ollama.com/api/chat. `docs/ollama-contract.json` records the subset used here.

A local Postman mock was generated from that subset, then extended with fixture model names for HTTP errors, invalid JSON, malformed content, missing/invalid citations, and a delayed response. Those are injected test scenarios, not actual Ollama model names or promises about model output.

## Run on Windows

Requires Postman CLI 1.70+ and the project's installed dev dependencies. No Postman sign-in or cloud publication is needed.

```powershell
postman simulation run postman/simulations/ollama/ollama.sim.yaml --port 4011 --no-history --output ndjson
```

In a second terminal:

```powershell
$env:PROVIDER_TEST_URL='http://127.0.0.1:4011/ollama'
.\.venv\Scripts\python.exe -m pytest tests/test_provider_integration.py -q
Remove-Item Env:PROVIDER_TEST_URL
```

Stop the simulation with Ctrl+C. One-port routing is used because the provider URL is configurable and the HTTP client explicitly avoids environment proxies. Check request events in the simulation terminal to verify the dependency was actually called.

The adapter is tested as real application code, through the actual HTTP client and a local server. These checks establish request serialization, response parsing, timeout handling, and fallback behavior against the stand-in. They do not establish real model availability, answer quality, prompt-injection resistance, or semantic faithfulness of generated answers.

The installed CLI did not implement `postman status`. Owner-workspace discovery was skipped; the stand-in was built from the provider documentation and no cloud resources were created.
