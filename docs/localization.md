# Localization workflow

Veksha treats the interface locale separately from the user's native and
learning languages. Every ISO language can be selected as a native or learning
language, but only interface locales listed in the localization policy can be
used for the application UI.

## Files and source of truth

- `veksha-backend/data/ui_locales.json` defines the interface locale tiers.
- `veksha-backend/i18n.py` → `UI_STRINGS` is the canonical English source.
- `veksha-extension/src/shared/i18n/strings.ts` → `EN` is the typed extension
  mirror. Its keys and values must exactly match `UI_STRINGS`; the architecture
  test enforces this.
- `veksha-backend/data/i18n_<locale>.json` is the reviewed, published catalogue.
- `veksha-backend/data/i18n_drafts/i18n_<locale>.json` is generated working
  output. Review and edit this file before publishing.
- `veksha-backend/data/i18n_source_hashes.json` records the English source hash
  that was reviewed for every published key.
- Extension and web builds copy published catalogues into
  `veksha-extension/src/shared/i18n/catalogs`. Do not maintain those bundled
  copies independently.

The policy has two tiers:

- `required`: selectable interface languages. Every required catalogue must be
  complete, current, tracked, and reviewed before a release can pass.
- `beta`: catalogues under translation or review. They do not appear in the
  normal interface language picker and do not block releases.

## Prerequisites

Run commands from the repository root unless a section says otherwise.
Generation needs a valid `OPENAI_API_KEY`; the model can be overridden with
`VEKSHA_CORE_V2_I18N_MODEL`.

```bash
export OPENAI_API_KEY=...
python veksha-backend/scripts/manage_i18n.py status
```

Status fields mean:

- `missing`: no non-empty translation exists for a source key;
- `stale`: the English source changed since that translation was published;
- `untracked`: a translation exists, but no reviewed source hash is recorded;
- `OK`: all three counts are zero.

## Adding a new beta interface language

1. Choose a normalized locale code: lowercase ISO 639 code, optionally followed
   by lowercase subtags separated with hyphens, for example `sv` or `pt-br`.
2. Add the code to `beta` in
   `veksha-backend/data/ui_locales.json`. Keep it out of `required` while work is
   incomplete. A locale must be in one of these lists before generation accepts
   it.
3. Confirm the policy and initial state:

   ```bash
   python veksha-backend/scripts/manage_i18n.py status
   ```

   A brand-new locale normally reports every source key as missing. A seed
   `i18n_<locale>.json` is optional; generation can start from an empty catalogue.
4. Generate a draft:

   ```bash
   python veksha-backend/scripts/manage_i18n.py generate sv
   ```

   Only missing or stale entries are requested, in batches of at most 50. The
   command fails if the provider omits a key or returns a translation with
   missing, renamed, or duplicated placeholders.
5. Review `veksha-backend/data/i18n_drafts/i18n_sv.json` before publishing:

   - preserve the meaning and UI intent, not just the words;
   - keep buttons and labels concise;
   - verify terminology is consistent across screens;
   - preserve product names and placeholders such as `{name}`, `{n}`, and
     `{language}` exactly;
   - check punctuation, plurals, text expansion, right-to-left layout where
     applicable, and language-specific capitalization;
   - replace any generated wording that is vague, overly literal, or unnatural.
6. Publish the reviewed draft:

   ```bash
   python veksha-backend/scripts/manage_i18n.py publish sv
   ```

   Publishing refuses incomplete catalogues and placeholder mismatches. It
   replaces the canonical JSON, records source hashes, and removes the draft.
7. Copy canonical assets into the extension and verify them:

   ```bash
   cd veksha-extension
   npm run sync-assets
   npm run typecheck
   npm run test:architecture
   cd ..
   python veksha-backend/scripts/manage_i18n.py status
   ```

8. Review the locale in the real interface. Because beta locales are hidden,
   temporarily move the locale from `beta` to `required` in your local,
   uncommitted `ui_locales.json`, run `npm run sync-assets`, and exercise every
   major surface. Restore the policy before committing if the locale is not yet
   ready for promotion.

Do not publish generated text without human review. Do not generate catalogues
synchronously in an end-user request.

## Promoting a beta locale to required

Promote only after the published beta catalogue has been reviewed in the actual
UI and its status is `OK`.

1. Regenerate if the status contains `missing` or `stale`, review the draft, and
   publish it again:

   ```bash
   python veksha-backend/scripts/manage_i18n.py generate sv
   python veksha-backend/scripts/manage_i18n.py publish sv
   ```

   If status contains only `untracked`, review the existing canonical catalogue
   and run `publish` directly. With no missing or stale entries, publishing the
   reviewed catalogue records the hashes without calling the model. Do not
   fabricate hashes manually.
2. Test the published beta catalogue locally, including onboarding, settings,
   overlays, validation errors, empty states, long content, and placeholder
   substitutions. For right-to-left languages, test layout and mixed-direction
   content explicitly.
3. Move the locale code from `beta` to `required` in
   `veksha-backend/data/ui_locales.json`. It must appear in exactly one tier.
4. Sync and run the release gates:

   ```bash
   cd veksha-extension
   npm run sync-assets
   npm run check:i18n
   npm run typecheck
   npm run test:architecture
   cd ..
   python veksha-backend/scripts/manage_i18n.py check
   ```

5. Confirm `check` exits successfully and the promoted locale reports
   `missing=0 stale=0 untracked=0 OK`. Commit the policy, canonical catalogue,
   source hashes, and synchronized bundled catalogue together.

After promotion, every English source change makes the locale stale and blocks
the required-catalogue release gate until a new translation is reviewed and
published.

## Adding or changing an English UI string

1. Add or update the same key and exact English value in both `UI_STRINGS` and
   the extension `EN` object.
2. Replace every visible hard-coded UI fragment with the typed catalogue key.
   Dynamic lists, language names, script names, dates, and numbers must use
   locale-aware formatters rather than English separators or labels.
3. Run `npm run test:architecture` in `veksha-extension`. The catalogue parity
   test fails if either source has a missing, extra, or different entry.
4. Run `status`. Every affected required locale should now be `missing` or
   `stale` instead of falsely reporting `OK`.
5. Generate, review, and publish every required locale, then sync assets and run
   the release gates. Beta locales may remain incomplete, but should be updated
   before their next review or promotion.

## Recovery and common failures

- If generation stops between batches, keep the draft and rerun the command.
  Already saved missing entries are retained.
- If the provider omits keys or breaks placeholders, no invalid batch is saved.
  Retry, or translate and review the affected draft entries manually.
- If `publish` reports a placeholder mismatch, compare placeholder names and
  counts with the English source; braces and spelling must be identical.
- If bundled catalogues differ from canonical catalogues, run
  `npm run sync-assets`; never fix only the bundled copy.
- If a published translation needs editorial correction without an English
  source change, edit the canonical `i18n_<locale>.json`, sync assets, and rerun
  the checks. Source hashes track English revisions, not translation wording.
