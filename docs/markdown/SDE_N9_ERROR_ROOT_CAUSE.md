# SDE nine-choice error

On 2026-11-14 the pinned snapshot rejected synthetic `n=9` before
generation with HTTP 400, code `integer_above_max_value`, parameter `n`,
and request ID `req_8255ef283f1c4411ab09e3289a529636`. The endpoint message
gave a maximum of 8. The Task 7 reservation was reconciled at zero
generation tokens against this validation response. The Task 6 reservation
remains unresolved because its original provider details were unavailable.

`grouped_3x3` uses three sequential requests on the same pinned snapshot
and concatenates all nine choices in request and choice order. Native
candidate selection and the single three-choice judge are preserved.
Request grouping changes the sampling and request accounting semantics.
The live case record labels this `SDE_GROUPED_3X3_REQUEST_ADAPTATION`.
Clinical execution requires approval for that variant and its evidence.
