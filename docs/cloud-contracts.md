# Cloud contract sources and stand-ins

REST adapters use the existing HTTPX dependency. They do not use OpenAI or a hosted LangChain service. LangGraph controls the application; `langchain-core` remains its dependency.

| Operation | Contract |
|---|---|
| Embedding | [Gemini batchEmbedContents](https://ai.google.dev/api/embeddings): model, content parts, taskType, outputDimensionality; embeddings[].values |
| Normalization | [Gemini embedding guidance](https://ai.google.dev/gemini-api/docs/embeddings): normalize reduced-dimensional gemini-embedding-001 vectors |
| Generation | [Gemini generateContent](https://ai.google.dev/api/generate-content): systemInstruction, contents, JSON response schema, candidate text, finish reason, usage |
| Index create/describe | [Pinecone 2025-10 control API](https://docs.pinecone.io/reference/api/2025-10/control-plane/create_index): dense dimensions, cosine, serverless spec, readiness, host |
| Upsert | [Pinecone upsert](https://docs.pinecone.io/reference/api/2025-10/data-plane/upsert): namespace, IDs, values, metadata, acknowledgement count |
| Query | [Pinecone query](https://docs.pinecone.io/reference/api/2025-10/data-plane/query): namespace, vector, topK, metadata, filters, scored matches |
| Public vendor search | [Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search): Bearer auth, query, include_domains, basic search, snippets, scores, source URLs and optional publication dates |

Credentials use headers: `x-goog-api-key` for Gemini, `Api-Key` for Pinecone. Pinecone requests pin `X-Pinecone-API-Version: 2025-10`. Redirects are not followed with credentials.

Orbit API discovery was consulted; its Pinecone controller and Gemini 1.5 candidates were outdated, so official contracts above were used. No owner-workspace search or cloud mock publication was performed; this Postman CLI does not implement `status`.

Stand-ins under `postman/mocks` model the paths used by the app and return 501 for unmodeled paths. Scenario controls are fixture-only. The stateful fixture uses prefixed asynchronous `pm.state` keys and separate test namespaces. One-port routing is explicit and HTTP clients ignore environment proxies.

For Tavily, Orbit search resolved the Tavily Search endpoint and its integration brief confirmed the official request shape and domain-filter behavior. Provider documentation and one live search were also checked. The Tavily stand-in models only the documented search subset and deliberate fault cases.
