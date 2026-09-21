# Manual Portal Compatibility

Use this checklist only to observe a real portal's shape. Never click Submit, create an employer account solely for testing, bypass authentication or CAPTCHA, upload a real person's documents, or interpret an observation as automated release evidence.

## Safe setup

1. Use public pages or an account the user already controls.
2. Prepare obviously synthetic text locally, but do not upload it to the real portal.
3. Record the portal family, URL, observation time, browser/runtime, and whether authentication was required.
4. Stop at the final review page or earlier. A portal warning, attestation, legal statement, identity check, CAPTCHA, or unexpected conditional field is a hard stop.

## Portal-family observations

### Workday-style multi-page flows

- Note account requirements, resume parsing, page count, conditional sections, save-and-return behavior, and whether the final review echoes every field.
- Check whether changing a parsed resume value alters later questions.
- Do not advance past the final review control.

### Greenhouse-style forms

- Note required contact fields, attachment types and limits, custom questions, consent fields, and whether validation occurs before the final action.
- Observe whether the confirmation surface would expose a receipt identifier; do not submit to discover it.

### Lever-style forms

- Note one-page versus staged behavior, attachment handling, optional profile links, duplicate-click controls, and field normalization.
- Treat any client-side normalization as a payload mutation requiring renewed review.

### Custom multi-page portals

- Map every page, conditional transition, session-expiry behavior, upload rejection surface, and irreversible control.
- Record what the portal does not echo. Missing fields are evidence limitations, not proof that the employer received them.

## Observation record

For each check, record only:

- portal family and public host;
- date, runtime, and browser;
- pages and field categories observed;
- conditional, normalization, expiry, upload, and final-review behavior;
- evidence limitations and the exact point where the check stopped.

Do not retain credentials, real answers, real uploaded bytes, hidden tokens, cookies, or personal data. Manual observations guide adapter compatibility; only the local fake-portal suite is automated release evidence.
