# VideoText Local Translation Pack

This optional pack enables offline local translation for VideoText 1.6. It does
not require an API key, OpenAI account, administrator rights, registry changes,
or a network connection during translation.

VideoText Core and all OCR features work without this pack. The installed model
directory uses approximately 500 MB (476.6 MiB) of disk space.

## Install

1. Close VideoText.
2. Copy the `m2m100-418m-int8` directory from this pack into:

   ```text
   %LOCALAPPDATA%\VideoText\models\translation\
   ```

3. Restart VideoText.

Local Translation becomes available only when the complete directory and its
`videotext-model.json` manifest are present. To remove it, close VideoText and
delete that directory. This does not affect OCR or cloud translation.

After installation, open VideoText and enable **Translate OCR text**. The Local
Translation option will list only locale mappings approved by the installed
manifest. If VideoText was open during installation or removal, restart it so
availability is refreshed.

## Supported local targets

- Portuguese — Brazil (`pt-BR`)
- Spanish — Latin America (`es-419`)
- Spanish — Spain (`es-ES`)
- Korean — South Korea (`ko-KR`)
- Dutch — Netherlands (`nl-NL`)

The current M2M100 model uses generic runtime Spanish and Portuguese tokens.
VideoText preserves the requested locale in provenance, but does not claim
region-specific terminology. All machine translations require human review.

The model pack performs translation locally after installation. It does not
download models, call OpenAI, or fall back to a cloud provider. OCR-model
availability is independent of this optional translation pack.

## For developers

The release archive contains the validated CTranslate2 int8 deployment model,
not the original Transformers/PyTorch source model or conversion environment.
Source-model conversion details are maintained separately in the repository's
developer documentation and are not part of user installation.
