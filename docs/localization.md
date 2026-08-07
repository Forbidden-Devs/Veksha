# Localization workflow

Veksha treats the interface locale separately from the user's native and
learning languages. The supported interface tiers live in
`veksha-backend/data/ui_locales.json`:

- `required` locales must be complete before a release;
- `beta` locales may be generated and reviewed without being offered as an
  interface choice yet;
- every ISO language remains available as a native or learning language.

The English `UI_STRINGS` dictionary in `veksha-backend/i18n.py` is the source
catalogue. Reviewed JSON files in `veksha-backend/data` are canonical; extension
and web builds copy them into the bundled extension catalogue automatically.

From `veksha-backend`:

```bash
python scripts/manage_i18n.py status
python scripts/manage_i18n.py check
python scripts/manage_i18n.py generate de
python scripts/manage_i18n.py publish de
```

`generate` requires `OPENAI_API_KEY`. It translates only missing strings and
strings whose tracked English source changed, in batches of at most 50. Output
is stored as a draft. `publish` validates completeness and placeholders before
replacing a reviewed catalogue and recording per-key source hashes.

Promote a locale from `beta` to `required` only after it is complete and has
been reviewed in the actual UI. Never generate synchronously in a user request.
