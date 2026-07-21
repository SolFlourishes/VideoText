Version 0.4.0 – Reconstruction Engine Complete

New Features

Complete OCR reconstruction workflow from candidate frames to semantic paragraphs.
Improved line reconstruction using bounding-box overlap rather than center-point grouping.
Reading-order reconstruction for complex slide layouts.
Paragraph reconstruction with support for wrapped numbered items.
Automatic inference of missing bullet lists when OCR omits bullet glyphs.
Inferred bullet classification as BULLET for downstream exporters.
Improved handling of multi-line numbered and bulleted content.

Enhancements

More robust geometric heuristics for layout interpretation.
Better preservation of author intent through semantic reconstruction.
Stable paragraph typing for export workflows.

Known Limitations

Decorative layouts may require future refinement.
Complex tables and SmartArt are not fully reconstructed.
Multi-column layouts are supported on a best-effort basis.

Next Milestone

Slide Consolidation: merge multiple observations of the same slide into a single canonical representation.
