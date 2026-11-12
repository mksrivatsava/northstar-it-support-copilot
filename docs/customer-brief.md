# Customer brief · Northstar Retail

Northstar is a fictional multi-office retailer. Employees repeatedly ask IT how to access internal systems, recover accounts, or troubleshoot collaboration tools. Support staff have runbooks, but finding the relevant passage and checking its relevance interrupts both employees and technicians.

The first pilot serves employees and IT administrators through an app on a local workstation with synthetic data. Cloud mode uses Gemini embeddings/generation and Pinecone retrieval; document text leaves the machine for embedding and answer generation. Employees need inspectable guidance. Administrators need to add runbooks without changing code and understand unanswered questions.

## Acceptance criteria

- A VPN question returns the managed-device steps with the actual source passage.
- An employee cannot retrieve or open a restricted administrator runbook.
- A new UTF-8 Markdown or text document becomes searchable immediately.
- An unsupported question produces a clear evidence gap, then an optional local ticket.
- No ticket is created as a side effect of asking a question.
- A live-status question does not turn an old runbook into an outage claim.
- Staff can inspect the route, retrieval, evidence check, retry, and final decision.
- A fixed evaluation can be rerun without contaminating product-usage metrics.

## Discovery questions for a real deployment

Who owns and approves each runbook? Which identities and groups govern access? How are old policies retired? What constitutes an acceptable answer versus an escalation? Which actions need approval? What support system is authoritative? Which data may be stored, and for how long?

## Pilot measurement plan

Start with a human-labeled set of historical, sanitized support questions. Measure citation support, answer usefulness, false-answer rate on unanswerable questions, retrieval recall, access leakage, latency, and actual escalations. Compare against keyword search and the existing support process. Ticket deflection requires a verified resolution event and a counterfactual baseline; the local 'answered' counter alone cannot establish it.

The synthetic acceptance cases in this repository validate implementation behavior. They do not establish business ROI or production readiness.
