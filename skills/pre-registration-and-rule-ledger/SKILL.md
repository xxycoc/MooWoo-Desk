---
name: pre-registration-and-rule-ledger
description: Use when documenting a new experiment, registering prompt provenance or recording an explicitly approved rule deviation.
---

# Pre-registration and rule ledger

## Inputs

`PREREGISTRATION.md`, the original `config/frozen-2026-11-17.json`,
`config/rule-ledger.jsonl`, source configuration and any explicitly authorized
change. Read `scripts/freeze_config.py`, `scripts/hash_prompts.py` and
`moowoo/rules.py` before changing experiment records.

## Procedure

1. Read the original hypotheses and all later addenda. Separate what was proposed, implemented, observed and abandoned.
2. For a new experiment only, commit the intended code, then generate a freeze using `scripts/freeze_config.py` with the experiment's date and verified universe/history inputs. Commit the freeze separately so its embedded code SHA is meaningful.
3. Compute `prompt_version` from `scripts/hash_prompts.py`. It hashes all `agents/*/system.md`, `schemas/rating.schema.json` and `agents/permissions.json`, including retired prompts, with normalized line endings and canonical JSON.
4. Register the actual hash in a dated addendum before order use. Do not copy a hash from memory or equate a hash of working files with a committed revision.
5. For an approved change, record its identifier, old/new rule, reason and timing through the existing rule-ledger contract. Preserve original artifacts; runtime validation applies recognized changes rather than silently overwriting the freeze.
6. Disclose changes that weaken the original commitment. SIZING-01 is such a deviation; it is not an original frozen parameter.

## Outputs

Dated provenance, immutable original artifacts and explicit change evidence that
preflight can validate. Local skills and README edits are outside the prompt hash.

## Limits

This skill does not authorize rule edits, autonomy or historical rewrites.
`agent.json` model choices and live cloud versions are not covered by this prompt
hash; record them separately. Existing addenda supersede stale descriptive docs,
but never make an unverified deployment or financial result true.

