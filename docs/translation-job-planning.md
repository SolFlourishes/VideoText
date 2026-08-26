# Translation Job and Output Planning

A translation job is immutable scope only: ordered source-item descriptors,
source and target language identifiers, one explicit canonical provider name,
and output preferences. It contains no source text, provider client, API key,
or workbook. Text evidence remains in translation source records and requests.

The planner is a pure transformation. It does not instantiate a provider,
translate text, access the filesystem, or create an Excel workbook. It supports
`BY_LANGUAGE`, `BY_SOURCE`, `COMBINED`, and `SEPARATE` grouping. Caller source
and language order is retained: language-major for `BY_LANGUAGE`, source-major
for the other modes.

Workbook identities are deterministic: `<job>:workbook:language:<language>`,
`<job>:workbook:source:<source>`, `<job>:workbook:combined`, or
`<job>:workbook:source:<source>:language:<language>`. Sheet identities are
`<job>:sheet:<source>:<language>`.

Names use common language display names where known, otherwise the exact valid
language identifier. Windows and Excel-invalid characters are removed, sheet
names are capped at 31 characters, and case-insensitive collisions receive
stable ` (2)`, ` (3)` suffixes. Planning does not inspect earlier runs; each job
is independent. Updating an existing workbook is intentionally deferred to
workbook population work.
