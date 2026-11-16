# SDE Chat Completions compatibility

**Task 7:** Native `n=9` fails because the provider caps `n` at 8.
Grouped `3 × n=3` passed on the pinned snapshot with nine complete
choices in three requests, 69 input tokens, 1,004 output tokens
(896 reasoning), and an estimated $0.00202525. The separate Task 7
diagnostic request was rejected before generation. See
[error root cause](SDE_N9_ERROR_ROOT_CAUSE.md). The details below describe
the earlier Task 6 observation.

**Live transport did not pass the two-request gate.** Both requests used
the synthetic instruction `Return exactly: SELECT 1`. They used
`gpt-5-mini-2025-08-07`, medium reasoning, `max_completion_tokens=512`,
and omitted `temperature` and `top_p`.

| Requested choices | Response | Usage |
|---:|---|---|
| 9 | HTTP 400 / SDK BadRequestError. No choices or usage returned. | 152 input / 4,608 output tokens reserved pending reconciliation |
| 3 | PASS, three complete choices. Response ID `chatcmpl-Ek12nnFVdGX7sBvBgIwPh6hyfPTcH` confirmed the pinned snapshot. | 23 input / 292 output tokens, of which 256 reasoning |

The existing transport retained the SDK exception type and HTTP status.
It did not preserve the provider error body, so the rejected parameter
remains unconfirmed. The shared Chat Completions documentation lists
`n`, while the live 400 establishes failure for this exact request.
[Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)

There is no successful compatibility marker and the patient-data path
remains blocked. The next transport experiment is a separately recorded
synthetic diagnostic that captures the provider's parameter and error code.
If the endpoint rejects nine choices, an explicitly approved grouped-request
variant could preserve nine candidates and the existing selection algorithm.
Its request semantics and cost would differ from native SDE. The current
runner retains its one-request requirement and pinned model.
