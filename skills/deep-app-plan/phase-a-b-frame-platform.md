# Phase A & B — Product Frame & Platform Interview

## Phase A — Frame the product

1. Restate the idea in two lines: target user, primary job.
2. **Grill the frame (`/grilling`):**
   - Who is the first user, and what is their primary job?
   - What does v1 do — and what does v1 deliberately leave out?
   - One measurable success signal.
   - Existing alternatives, and why the user passes on them.
3. **Cut milestones:** M0 walking skeleton, then one milestone per deployable capability.
4. Write the project ledger.
5. **Gate:** the user explicitly signs off the v1 scope.

## Phase B — Platform interview (one-way doors)

Ask everything the user has not already stated in **one batched `AskUserQuestion` pass**, each with a recommended default:

- **Home:** GitHub/GitLab, public/private, org, licence (MIT default).
- **Hosting:** Pages / Workers / Vercel / Railway / Supabase / Firebase.
- **Database:** Postgres / SQLite / D1 / Firestore; backups and migration path.
- **Auth:** email+password / provider OAuth / managed (Clerk, Supabase Auth).
- **CI:** GitHub Actions running the contract on push/PR.
- **Auto-deploy:** platform git integration vs. Actions CLI deploy; rollback mechanism.
- **Domain & secrets:** DNS holder; where env vars live and who can read them.
- **Spend policy:** build-time, runtime, hosting ceiling ($ cap).
- **Reality check & observability:** expected scale, solo/team, lifespan, error tracking.

Record the answers as ADRs via `/domain-modeling` and in the ledger's Platform block.

**Gate:** the user confirms the platform.
