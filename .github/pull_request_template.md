## What changed and why

## UX checklist (skip if no UI change)

Based on the [BYU–Hawaii UX and Design Guidelines](https://marcom.byuh.edu/websites/ux-and-design-guidelines).

- [ ] **Clear:** a first-time user can tell what this screen is for and what to do next
- [ ] **Simple:** anything that doesn't need to be there has been removed
- [ ] **Actionable:** there is one obvious primary action, styled like every other primary action
- [ ] **Fast:** no extra clicks or typing where a chip or default would do
- [ ] **Accessible:** real headings, descriptive link and button text, alt text, AA contrast, keyboard operable, not color alone
- [ ] **Mobile first:** checked at phone width; tap targets are at least 44px

## Data checks (skip if no pipeline or schema change)

- [ ] New user-owned tables have RLS enabled and forced, plus a policy and a test
- [ ] Ingestion writes stay idempotent
- [ ] No Spotify content beyond IDs/ISRCs is stored
