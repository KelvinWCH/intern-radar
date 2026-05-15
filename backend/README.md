# backend

FastAPI app, scrape worker and CLI, all in the `job_backend` package. Setup is in the
[main README](../README.md#local-development).

## Where things are

| Folder               | What's in it                                                                  |
| -------------------- | ----------------------------------------------------------------------------- |
| `scrape/github/`     | one file per GitHub internship list, shared markdown parsing                  |
| `scrape/<provider>/` | adapters for public job boards (greenhouse, lever, ashby, workday, oracle...) |
| `scrape/companies/`  | `companies.json`, the list of company boards                                  |
| `scrape/pipeline/`   | one import: fetch, filter, read pages, extract, save, close stale postings    |
| `scrape/utils/`      | http client, per host pacing, page reader, headless browser                   |
| `scrape/worker/`     | the scheduler, `schedules.json` and the per source child processes            |
| `jobs/`              | saved jobs, browsing and filters, application status, tailoring runs          |
| `resumes/`           | research, writers, reviewer, latex rendering, pdf checks                      |
| `profile/`           | your profile                                                                  |
| `matching/`          | embedding based match scores                                                  |
| `persistence/`       | postgres access, json records, migrations                                     |
| `embedder/`          | the optional gpu embedding sidecar (next to `src/`, not in it)                |

Each feature folder keeps its models in `models.py` and its constants, AI prompts included, in
`constants.py`.

## Commands

```sh
python -m job_backend.cli --repo simplify-summer2027   # one github list
python -m job_backend.cli --all-repos
python -m job_backend.cli --list-companies             # no network
python -m job_backend.cli --company 1password
python -m job_backend.cli --all-companies --use-ai     # ai extraction is opt in
python -m job_backend.scrape.worker --show-schedule    # print the schedule and exit
python -m job_backend.scrape.worker --check-browser    # make sure headless chromium starts
```

[docs/brag-sheet-prompts.md](docs/brag-sheet-prompts.md) has two prompts you can give another AI
to turn a project repo or a job into a brag sheet for your profile.

## Tests

```sh
python -m ruff check .
python -m ruff format --check .
python -m pyright
python -m pytest
```

Tests never touch the network or a real database. Set `JOB_TEST_DATABASE_URL` to a throwaway
PostgreSQL server to also run the postgres tests.
