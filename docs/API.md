# Gatekeeper REST API (contract)

Base: `http://localhost:8000/api`. All bodies JSON, all shapes are Pydantic v2 models in `backend/app/schemas.py`.
"Lead login" = community selector: every lead-side route is scoped by `{slug}` in the path (no auth beyond that — hackathon cut).

## Communities & settings
- `GET /communities` → `[{id, slug, name}]`
- `GET /communities/{slug}` → `Community`
- `PUT /communities/{slug}/settings` body `{rules:[{id?, text}], categories:[{slug, name, quota, bypass_quota}], reconsider_cooldown_days}` → `Community`

`Community = {id, slug, name, description, rules:[{id, text}], reconsider_cooldown_days, categories:[CategoryQuota]}`
`CategoryQuota = {slug, name, quota, bypass_quota, used, remaining, waitlisted}` (`used` = accepted count; `remaining = max(quota-used,0)`)

## Applications
- `POST /communities/{slug}/apply` (public) body `ApplyIn = {name, email, phone?, github?, devpost?, chat_handle?, what_build, category}` → `ApplicantDetail` (synchronous; evidence gathering has bounded timeouts, total < ~20s)
- `GET /communities/{slug}/applicants?status=&category=&q=` → `[ApplicantSummary]` newest first
- `GET /communities/{slug}/queue` → `[ApplicantDetail]` (status `ask`, oldest first)
- `GET /applicants/{id}` → `ApplicantDetail`
- `POST /applicants/{id}/decision` body `{verdict: "accept"|"ask_more"|"decline", reason_category?: ReasonCategory, note?}` → `{applicant: ApplicantDetail, model: ModelInfo}` (decline requires reason_category; retrains the history model synchronously)
- `POST /applicants/{id}/recheck` → `ApplicantDetail` (400 with `detail` if not reconsiderable / cool-down not over)
- `POST /communities/{slug}/recheck-due` → `{checked: int, changed: [ApplicantSummary]}` (same job APScheduler runs daily)
- `POST /demo/reset` → `{ok: true, applicants: int, queue: int}` (restores seed data; disabled with `DEMO_RESET=0`)

`ReasonCategory = "skill_gap"|"minor_issue"|"capacity"|"scam_abuse"|"rules_mismatch"`
`Status = "accepted"|"ask"|"declined"|"waitlisted"`

```
ApplicantSummary = {id, name, category, status, final_score, confidence, top_reason, decision_source: "auto"|"lead", created_at, is_seed, reconsidered: bool}

ApplicantDetail = ApplicantSummary + {
  community_slug, email, phone_masked, github, devpost, chat_handle, what_build, decided_at,
  decline_reason: ReasonCategory|null,
  recommendation: {
    verdict: "accept"|"ask"|"decline", confidence: float(0-1), final_score: float(0-1),
    reasons: [string],                      # human readable, most important first
    route_rule: string,                     # which router rule fired, e.g. "blocklist_confirmed", "disagreement", "score_accept"
    disagreement: bool,
    llm: {status: "live"|"cached"|"unavailable", provider: string|null, model: string|null, error: string|null},
    rule_score: float,
    rule_checks: [{rule_id, rule, score: float, verdict: "pass"|"unclear"|"fail", reason, quote: string|null, source: "llm"|"heuristic"}],
    history: {available: bool, p_accept: float|null, n_training: int, top_features: [{feature, value, contribution}]},
    evidence: {
      github:   {status: "live"|"simulated"|"not_provided"|"not_found"|"unavailable", login?, account_age_days?, public_repos?, followers?, recent_push_days?, url?},
      devpost:  {status: ..., projects?: int, wins?: int, sample?: [{name, url}]},
      stopforumspam: {status: ..., email_appears?: bool, username_appears?: bool, confidence?: float},
      blocklist: {hit: bool, matches: [{entry_id, identifier_type, status, reporting_community, evidence, links: [string], reported_at}]}
    },
    quota: {category, quota, used, remaining, bypass_quota, outcome: "seat"|"waitlisted"|null, waitlist_rank: int|null}
  },
  reconsideration: {eligible: bool, reconsider_after: datetime|null, previous: {declined_at, reason_category}|null, note: string|null},
  decisions: [{verdict, reason_category, note, source: "lead"|"auto"|"seed", created_at}]
}
```

## Notifications ("notify lead")
- `GET /communities/{slug}/notifications` → `[{id, applicant_id, applicant_name, kind: "needs_review"|"reconsidered"|"blocklist_hit", message, read, created_at}]`
- `POST /notifications/{id}/read` → `{ok: true}`

## History model
- `GET /communities/{slug}/model` → `ModelInfo = {available, n_decisions, n_accept, n_decline, trained_at, coefficients: [{feature, weight}]}`
- `POST /communities/{slug}/model/retrain` → `ModelInfo`

## Shared blocklist (read through Postgres RLS as the community)
- `GET /communities/{slug}/blocklist` → `[BlockEntry]` (own pending + all confirmed/appealed; never others' pending)
- `POST /communities/{slug}/blocklist` body `{identifier_type: "phone"|"email"|"github"|"handle", identifier, evidence, links: [string]}` → `BlockEntry` (status pending)
- `POST /communities/{slug}/blocklist/{id}/confirm` | `/remove` → `BlockEntry` (only reporting community)
- `POST /appeals` (public) body `{identifier_type, identifier, contact, message}` → `{id, status, matched: bool}`
- `POST /communities/{slug}/appeals/{id}/resolve` body `{outcome: "upheld"|"rejected"}` → `BlockEntry` (upheld → entry removed; rejected → back to confirmed)

`BlockEntry = {id, identifier_type, identifier_hash_prefix, evidence, links, reporting_community: {slug, name}, is_own: bool, status: "pending"|"confirmed"|"appealed"|"removed", created_at, appeals: [{id, contact, message, status: "open"|"upheld"|"rejected", created_at}]}`

## Evaluation
- `GET /eval` → latest report (written by `python -m app.eval` to `backend/data/eval_report.json`) or 404
- `POST /eval/run` → runs it and returns the report
```
EvalReport = {generated_at, test_set: {n, n_accept, n_decline, n_scam, n_edge, source}, train_set: {n, source},
  variants: [{name: "rules_only"|"rules_plus_history", accuracy, accept_precision, accept_recall, decline_precision, decline_recall,
              false_block_rate, ask_rate, accuracy_on_decided, confusion: {...}, confusion_matrix: {accept|decline: {accept, ask, decline}},
              by_kind: {kind: {n, accuracy, ask_rate}}, n}],
  notes: [string], edge_cases: [{kind, labels, rules_only_accuracy, rules_plus_history_accuracy}]}
```

## Misc
- `GET /health` → `{ok, db, llm: {available, provider, model, label, verified, error, calls_made, max_calls}, github_token: bool}`
- `llm.verified` is false until a completion call has succeeded or failed since startup; `llm.available` is true only when the provider is configured and the latest completion succeeded.
- Cursor CLI is selected by default when `CURSOR_API_KEY` is set; otherwise Gemini is the default. `LLM_PROVIDER` can select a provider explicitly. Cursor uses `LLM_MODEL` (default `gemini-3.7-flash-high`); `cursor-grok-4.5-high-fast` is an available Grok 4.5 option, and `CURSOR_MODEL` remains a fallback. Provider attempts, including retries, share a process-wide cap of 40 by default (`LLM_MAX_CALLS`).
- Only live form submissions call an LLM. Re-checks reuse stored live rule checks with `status: "cached"` and the original provider; otherwise they use heuristic checks. Evaluation uses heuristic checks and makes zero LLM calls.
- Stretch: `POST /messages/check` body `{text}` → `{scam_probability, label, top_terms: [{term, weight}], draft_removal}`
