# OCR Engine Corpus v2

This nine-frame Sample2 corpus is a **provisional baseline**, not a
human-verified benchmark. Every reference was imported from the accepted Task
32E preprocessing manifest and is marked `Pending Human Verification`.

Review workflow: inspect the saved source image; transcribe visible text without
copying engine output; record ambiguous content; perform a second image review;
then fill reviewer, verification date, and a verified status. One reviewer may
perform both passes, but that limitation must be recorded in `notes`.

The scoring policy is NFC, collapsed whitespace, preserved case/punctuation/
bullets, and no engine-specific normalization. Until every applicable record is
verified, CER/WER is exploratory comparison against this baseline only.

The corpus covers title, dense text, small text, lower contrast, structured
sections, progressive content, punctuation, and graphic-overlay-like ruled
backgrounds. It does not yet cover true tables, charts/diagrams, standard bullet
lists, or independently selected compression artifacts.
