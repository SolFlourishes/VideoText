# VideoText 1.8 — AI-Assisted Understanding Foundation

## Overview

VideoText 1.8 lays an evidence-preserving foundation for visual information
OCR alone cannot represent reliably, including chart relationships, diagrams,
tables, timelines, and meaningful figures.

`source frame → OCR/readable Presentation → optional visual-analysis evidence layer`

AI-derived interpretation is additive and never overwrites source frames, raw
OCR, or readable OCR output.

## What is user-visible now

- Batch Name consistency across normal batch translation and existing-results translation
- A substantially smaller, faster-starting portable application on the validation machine
- Preserved OCR, export, translation, Translation Review, replay, and batch workflows

Production visual interpretation is not exposed through normal GUI controls.

## Architecture and local-first direction

The release adds exact-frame provenance, deterministic candidate detection,
provider-neutral observations, versioned JSON persistence, Markdown reporting,
replay projection, and safe failure/cancellation. Optional no-admin capability
packs keep heavyweight models and runtimes outside Core and persistent across
upgrades. Local/offline operation remains a first-class requirement.

Qwen evaluation was promising on synthetic cases and runtime issues were
resolved, but dense real time-series relationship extraction did not meet the
production quality gate. The provider remains development-only rather than
shipping a known limitation.

## Packaging and validation

The true one-folder build measured 742,840,643 bytes and roughly 1–2 second
startup on the validation machine, versus 1,600,126,597 bytes and about 31
seconds before. Results vary by system; portable/no-admin operation remains.

Release gates cover regression tests, compileall, diff/preflight/`pip check`,
clean packaging, startup/network observation, OCR, exports, replay, local
translation, batch regression coverage, and copied-folder portability. Batch
GUI variants are described as automated unless explicitly run manually.

## GitHub release notes

VideoText 1.8 introduces the evidence-preserving AI-Assisted Understanding
Foundation for future chart, diagram, table, and figure interpretation. It
adds provider-neutral visual contracts, deterministic candidate analysis,
replay/persistence/reporting foundations, and modular local-first capability
packs without overwriting OCR or source evidence.

This release also adds Batch Name consistency to normal batch translation and
a true one-folder portable package that measured substantially smaller and
faster-starting on the validation machine. Existing OCR, export, translation,
review, replay, and batch workflows remain supported.

The evaluated local visual model did not meet the dense real-chart quality
gate. Production visual interpretation is not enabled in the normal GUI, and
visual models/runtimes are not bundled with VideoText Core.

## Release Artifact

- File: `VideoText-1.8.0-Windows-Portable.zip`
- Size: `276,528,997 bytes` (~263.7 MiB)
- SHA-256: `F007FEEBCDD28BD2CA67C50342656FBA7B2B8E03896CCAA98C4F8B4CE308B1B9`
- Git tag: `v1.8.0`