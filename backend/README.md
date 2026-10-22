# Gatekeeper backend

Python 3.11 + FastAPI + PostgreSQL (plain SQL through psycopg). Install with
`python3.11 -m venv .venv && .venv/bin/pip install -r requirements.txt`, copy
`.env.example` to `.env`, then run `./run.sh`. `make test` uses the separate
`gatekeeper_test` database and disables the scheduler.

History/rules intentionally use scikit-learn, numpy, and deterministic token
overlap. Torch and sentence-transformers are intentionally not dependencies:
they are too heavy for this hackathon timebox.
