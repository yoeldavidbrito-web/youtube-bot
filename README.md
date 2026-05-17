# YouTube Bot

Automation project for generating, reviewing, and uploading English-language true crime Shorts.

## What it does

- Generates short scripts with Gemini
- Produces narration audio and timestamps
- Builds metadata and hashtags
- Renders Shorts with local composition plus optional AI video backgrounds
- Runs quality checks before upload
- Uploads approved videos privately to YouTube

## Public site files

The `docs/` folder contains the public legal pages used for platform integrations:

- `docs/privacy.html`
- `docs/terms.html`

## Sensitive files

Secrets, tokens, generated media, and local artifacts are excluded through `.gitignore`.
