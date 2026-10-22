# Gatekeeper

Application vetting for community leads (London Grok Bot Community Engineering hackathon, Track 1 · Vetting & moderation).

Applicants are scored against the community's written rules and public evidence (GitHub, Devpost, StopForumSpam, a shared blocklist). A logistic-regression model trained on the lead's own past decisions adjusts each call, and every applicant is routed to accept, ask (the lead's review queue) or decline, always with reasons. Seats are capped per category, and declines for a skill gap or a minor issue are reconsidered after a cool-down.

Work in progress. The full setup, architecture and demo script will be added here.

- API contract: [docs/API.md](docs/API.md)
- License: MIT
