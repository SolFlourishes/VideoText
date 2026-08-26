# VideoText Use Cases

VideoText extracts text that appears visually within video and converts it into structured, usable information.

This document is a living catalog of problems VideoText can solve or may be able to solve as the project develops. It is intended to support product development, documentation, stakeholder discussions, future marketing, and market validation.

Use cases are included because they represent plausible, concrete applications of VideoText—not simply because a feature could theoretically be used that way.

## Status Definitions

**Current** — Supported by the current VideoText application.

**In Development** — Supported by capabilities currently being developed.

**Planned** — A recognized use case that fits the VideoText architecture but requires future development.

**Exploratory** — A potentially valuable use that has been identified but has not yet been validated or placed on the development roadmap.

---

# 1. Extract On-Screen Text from Video

**Status:** Current

## Problem

Important information can appear visually within a video without existing anywhere as searchable or reusable text. Manually reviewing a video and transcribing every instance of on-screen text can be slow and error-prone.

Examples include:

* Presentation slides
* Titles and headings
* Names and credentials
* Definitions
* Labels
* Statistics
* Instructions
* Signs
* Screen recordings
* Other text displayed within the video

## Users

Potential users include:

* Researchers
* Faculty
* Instructional designers
* Educational technologists
* Accessibility professionals
* Media professionals
* Archivists
* Content creators

## VideoText Workflow

VideoText analyzes video frames, identifies text using OCR, associates detected text with its location in the video, and produces structured results.

## Outputs

Depending on the selected workflow, extracted information can be exported into structured formats such as:

* CSV
* Markdown
* Excel

## Value

VideoText turns text that is otherwise trapped inside video into information that can be searched, reviewed, analyzed, and reused.

---

# 2. Create a Searchable Record of Video Content

**Status:** Current / Developing

## Problem

Traditional transcripts primarily capture spoken language. They may not contain information communicated visually through slides, labels, title cards, diagrams, demonstrations, or other on-screen text.

As a result, searching a transcript does not necessarily search all of the information contained in the video.

## Users

Potential users include:

* Researchers
* Faculty
* Students
* Librarians
* Archivists
* Educational technologists
* Media teams

## VideoText Workflow

VideoText extracts on-screen text and associates it with timestamps, creating a structured record of when visual text appears.

## Output

A searchable dataset connecting text with locations in the source video.

## Value

Users can locate information that may never appear in the spoken transcript.

---

# 3. Analyze Collections of Video for Research

**Status:** Current / Developing

## Problem

Researchers working with video collections may need to identify or analyze text appearing across many recordings.

Manually reviewing each video can make large-scale analysis impractical.

Examples could include studying:

* Educational presentations
* Recorded lectures
* Public meetings
* Historical video
* News broadcasts
* Screen recordings
* Training materials

## Users

Potential users include:

* Researchers
* Graduate students
* Digital humanities scholars
* Education researchers
* Archivists

## VideoText Workflow

VideoText extracts timestamped visual text into structured formats that can be reviewed or incorporated into subsequent qualitative or quantitative analysis.

## Outputs

* CSV datasets
* Excel workbooks
* Markdown
* Preserved OCR evidence and quality information

## Value

VideoText can transform visual text in video into structured research data while preserving a connection to the original source.

---

# 4. Identify Visual Information Missing from Captions or Transcripts

**Status:** Developing / Planned

## Problem

A video may technically have captions while still communicating important information visually that is not contained in the spoken audio.

For example, a presenter might say:

> "As you can see from these results..."

while a chart containing the actual results appears on screen.

A caption or speech transcript records the sentence but not necessarily the information the viewer was expected to see.

## Users

Potential users include:

* Digital accessibility professionals
* Faculty
* Instructional designers
* Educational technologists
* Media teams
* Disability support personnel

## VideoText Workflow

VideoText identifies text appearing visually in the video and creates a timestamped record that can be compared with other representations of the video's content.

Future workflows may help reviewers identify information that is visually present but not otherwise communicated.

## Value

This can help identify accessibility gaps that would not be discovered by checking captions alone.

---

# 5. Create an Accessibility Addendum for Third-Party Video

**Status:** Planned

## Problem

Educational institutions frequently use videos they do not own or control.

A third-party video may have captions but still contain meaningful visual information that is not communicated through narration or audio description.

Because the institution does not own the source video, directly remediating the video may not be possible.

An accessible companion resource may therefore be needed.

## Users

Potential users include:

* Higher education accessibility offices
* Faculty
* Instructional designers
* Educational technologists
* Libraries
* Online learning teams
* Training organizations

## Example

An instructor links to an external educational video.

The video is captioned, but during the presentation it displays:

* Definitions
* Charts
* Statistics
* Diagrams
* Names
* Instructions

Some of this information is never spoken aloud.

The institution cannot modify the original video.

VideoText could help create an accessible document containing the missing information.

## Future VideoText Workflow

**Analyze → Identify → Review → Remediate → Document**

VideoText would:

1. Analyze the video for visual information.
2. Identify potentially meaningful on-screen text.
3. Preserve timestamps and source evidence.
4. Present identified material for human review.
5. Allow a reviewer to accept, edit, describe, or exclude material.
6. Assemble verified information into an accessible companion document.

Possible review actions could include:

* Accept Text
* Edit Text
* Add Description
* Not Relevant

## Future Outputs

Potential outputs could include:

* Accessible Word document
* Accessible HTML
* Accessible PDF
* Structured accessibility record

## Value

The institution can provide access to important visual information even when it cannot modify the original video.

A useful way of describing this use case is:

> **Make the information inside video accessible—even when you don't own the video.**

---

# 6. Human Verification of Extracted Video Text

**Status:** Planned

## Problem

OCR is probabilistic. High-quality automated extraction can reduce manual work, but some content will still require human judgment.

For accessibility, research, archival, and other high-value uses, users may need to distinguish between machine-generated text and text that has been reviewed by a person.

## Users

Potential users include:

* Accessibility professionals
* Researchers
* Archivists
* Instructional designers
* Localization teams
* Quality-assurance staff

## Future VideoText Workflow

A review workspace could present:

* Extracted text
* OCR confidence
* Timestamp
* Source frame or region
* Relevant provenance

Reviewers could then:

* Accept
* Edit
* Flag
* Skip

The original OCR evidence would remain preserved rather than being overwritten by the corrected text.

## Output

A verified text layer with preserved provenance and reviewer decisions.

## Value

VideoText can combine automation with human judgment rather than forcing users to choose between completely manual transcription and unquestioned machine output.

---

# 7. Translate On-Screen Text in Video

**Status:** Current

## Problem

Translation workflows commonly focus on spoken dialogue and captions.

Videos can also contain significant written information, including:

* Presentation slides
* Interface text
* Signs
* Labels
* Names and titles
* Instructions
* Charts
* Definitions

That visual information may also need translation.

## Users

Potential users include:

* Educational institutions
* Localization teams
* International organizations
* Training departments
* Content creators
* Researchers

## VideoText Workflow

VideoText can use extracted source text as the basis for a separate translation layer while preserving the original OCR evidence.

The source text remains intact rather than being replaced by its translation.

## Outputs

Structured source and translated text associated with the relevant video location and timestamp.

## Local Translation Direction

VideoText's local translation foundation is designed for optional approved
offline model packs. When a validated local model is installed, translation can
run without a cloud account, API key, or per-request charge, while preserving
the same source evidence and human-review workflow. Language-family support does
not imply a language is installed or operationally validated; all machine
translations still require human review.

## Value

VideoText can identify written information that may otherwise be missed by workflows centered on captions or speech transcription.

---

# 8. Support Video Localization

**Status:** Planned

## Problem

Organizations may need to localize existing video libraries into additional languages.

Speech and caption translation address only part of the problem. Important written information may be embedded directly into the video.

## Users

Potential users include:

* Universities
* Training organizations
* Localization teams
* International organizations
* Media producers
* Corporate learning departments

## Example

A training organization has hundreds of English-language instructional videos that need to be offered in Spanish.

The narration and captions can be translated through existing tools, but the videos also contain:

* Slides
* Software interfaces
* Instructions
* Labels
* Definitions
* Title cards

VideoText could identify these elements and produce a structured translation record for localization staff.

## Value

VideoText can complement speech-translation systems by addressing the visual text layer of video localization.

---

# 9. Preserve Evidence While Using AI-Assisted Workflows

**Status:** Developing / Planned

## Problem

Automated systems can improve extracted information, but replacing source evidence with AI-generated or corrected content can make it difficult to determine what originally came from the video.

This is particularly important for:

* Research
* Accessibility
* Archival work
* Quality assurance
* Human verification

## VideoText Approach

VideoText preserves source OCR evidence separately from subsequent interpretation, correction, translation, or AI-assisted enrichment.

Future AI-assisted capabilities may suggest:

* Corrected text
* Translations
* Visual descriptions
* Other enriched information

Those suggestions should not silently replace the preserved source evidence.

## Value

Users retain a traceable relationship between the source video, machine extraction, human decisions, and subsequent derived information.

---

# Guiding Principle

Across these use cases, VideoText is not simply an OCR application.

Its broader purpose is to:

> **Turn information embedded visually in video into structured, reviewable, portable text while preserving its connection to the source.**

Different users can then apply that information to research, accessibility, translation, localization, education, archiving, or other workflows.

---

# Maintaining This Document

`USE_CASES.md` is a living document.

As VideoText development continues, newly discovered uses should be evaluated for inclusion here.

A use case should be added when:

1. It represents a concrete problem a real user or organization could encounter.
2. VideoText provides a meaningful part of the solution.
3. The use follows reasonably from current or planned VideoText capabilities.
4. The use can be described without overstating what VideoText currently does.

New entries should identify their development status clearly so that planned or exploratory capabilities are not mistaken for currently available features.

Use cases may later inform:

* Product requirements
* Development priorities
* Documentation
* Demonstrations
* Accessibility planning
* Stakeholder discussions
* Grant or proposal language
* Website content
* Marketing
* Market segmentation
* Market-validation studies

The purpose of this document is not to make VideoText appear to do more than it does.

It is to maintain a clear record of **why VideoText may be useful and which real problems its evolving capabilities can solve.**

---

# 10. Risk-Prioritized Human Translation Review

**Status:** Current

## Problem

Large translation jobs may contain hundreds or thousands of machine-translated
text regions. Human review is still required, but treating every translation as
equally risky makes review inefficient.

## How VideoText Helps

VideoText preserves every machine translation while applying deterministic
review-warning signals to identify items that particularly warrant human
attention. Version 1.6 implements translation-failure, suspicious
source-text-copying, numeric-mismatch, and structural-mismatch signals. Weak
source OCR is planned only when preserved OCR evidence can be linked safely.

## Human Role

All translations remain subject to human review. Warnings prioritize attention;
they do not verify correctness. Reviewers use the existing Original Text,
Initial AI Translation, Modified Translation, and Verified workflow to inspect
and correct output.

## Audience

Potential audiences include accessibility teams, instructional designers,
localization teams, faculty-development units, educational institutions, and
organizations processing large multilingual video collections.

## Value

VideoText supports efficient human review without presenting heuristic warnings
as calibrated translation confidence or automated verification.

---

# 11. Translate an Existing Library Without Repeating OCR

**Status:** Current

## Problem

An organization may already have a library of completed VideoText results and
later need translations for additional languages. Reprocessing every original
video would repeat costly OCR work and create unnecessary duplicate evidence.

## VideoText Workflow

VideoText can select multiple completed result folders, reconstruct their
Presentations from preserved trusted reading-order caches, and pass them to the
existing translation pipeline. Users retain the existing provider, target
locale, grouping, export, provenance, and review-intelligence choices.

## Outputs and Evidence

Translation artifacts are created in a separate workspace. Source result
folders, source OCR, and reading-order checkpoints remain unchanged. Invalid or
duplicate selections and partial translation failures remain visible.

## Value

Localization teams can add languages to an already processed video collection
without rerunning video analysis or OCR, while preserving the original evidence
and human-review workflow.
