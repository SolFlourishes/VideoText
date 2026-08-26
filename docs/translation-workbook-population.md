# Translation Workbook Population

Translation workbook population consumes completed, immutable translation
evidence. It does not choose OCR source text, create requests, invoke a provider,
or retry failed work. A worksheet row supplies the exact upstream-selected source
text and its stable request, source, target-language, and ordering identities.

The writer uses the planned filenames, workbook IDs, and sheet names from the
translation output plan. All four grouping modes are supported. It creates only
new `.xlsx` files in the caller-provided output directory and fails rather than
overwriting an existing review workbook. Updating or merging a reviewed workbook
is intentionally deferred.

The visible review table remains:

1. Slide
2. Original Text
3. Initial AI Translation
4. Modified Translation
5. Verified

Only a successful translation populates **Initial AI Translation**. Modified
Translation and Verified are always blank and editable in a newly created
workbook. Failed translations leave the visible AI cell blank; their status,
safe error text, request/source identities, provider/model values, and safe
provider metadata are retained in the hidden `_VideoText_Metadata` worksheet.

The matching policy is strict: every planned row must have exactly one result
with the matching request ID, target language, source reference, and selected
source text. Missing, duplicate, mismatched, or extra result evidence stops
generation rather than guessing. The writer uses no provider registry or SDK.
