# Synthetic visual-understanding evaluation corpus

These small synthetic PNGs and versioned JSON cases exercise VideoText-specific
visual relationships. They are not a general-purpose VLM benchmark and do not
establish production readiness. Run `generate_images.py` to reproduce the PNGs.

Real frames must remain outside Git. Put local JSON/PNG cases in an ignored
`visual-evaluation-local/` directory or pass any explicit local directory with
`--cases`. Each case image must be a PNG beside its JSON case file; the loader
does not search recursively or permit paths outside that directory.

Example development evaluation:

```powershell
python tools/evaluate_visual_understanding.py `
    --pack D:\VideoTextModels\candidate\visual-capability-pack.json `
    --cases tests\fixtures\visual_evaluation `
    --output D:\VideoTextVisualEvaluation\candidate `
    --application-version 1.8.0-dev
```

`--application-version` is an explicit development-only pack preflight value.
It does not modify `APP_RELEASE`, which remains the released application version.
The tool never downloads a runtime, model, projector, or pack.
