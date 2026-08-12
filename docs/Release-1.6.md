# VideoText 1.6.0 — Translation Foundation

## What's New

VideoText 1.6 adds optional translation after canonical OCR processing. Users
can translate one or more videos to multiple locales, create Translation Review
Workbooks plus CSV/Markdown views, and prioritize human review with explicit
textual review statuses. Translation artifacts remain organized with the OCR
run that supplied their source evidence.

## Local Translation

The optional Local Translation Pack enables offline CTranslate2/M2M100
translation without an API key or cloud account. Validated targets are
Portuguese — Brazil, Spanish — Latin America, Spanish — Spain, Korean — South
Korea, and Dutch — Netherlands. VideoText Core works without the pack.

## OpenAI Cloud

OpenAI Cloud is optional and bring-your-own-key. VideoText displays a disclosure
before transmitting OCR-derived text, requests a masked session-only API key,
and does not persist, log, or export it. Video/image data are not sent by the
translation provider. Internet access is required and API charges may apply.

## Human Review

OCR remains canonical and translation never overwrites it. Machine translations
are never automatically verified. Normal Review is not proof of correctness;
Review Recommended prioritizes deterministic warning signals for inspection.

## Accessibility

Version 1.6 improves keyboard navigation for translation and locale selection,
uses textual rather than color-only review status, clarifies OCR versus
translation outputs, and adds `Help → Accessibility` with keyboard guidance,
output practices, and known limitations. These improvements are
standards-informed and are not a claim of formal certification.

## Upgrade Notes

Existing 1.5 OCR workflows remain available. Translation is off by default.
Install the optional model pack only if offline local translation is needed;
OpenAI Cloud requires a user-supplied key each session.

## Known Limitations

- OCR and all machine translations require human review.
- Local M2M100 translation uses generic Spanish and Portuguese runtime tokens;
  exact regional vocabulary is not guaranteed.
- Canadian English is available through OpenAI Cloud, not the current local
  pack.
- OpenAI Cloud requires connectivity and may incur charges.
- Local language expansion, model management, additional providers, and richer
  verification remain future work.
