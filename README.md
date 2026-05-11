# Intern Radar

Intern Radar pulls new Canadian internship postings from public GitHub lists and 186 company job
boards every few hours, ranks them against your profile, tracks your applications, and writes a
tailored one page resume and cover letter for a posting with a few separate AI agents.

![A tailoring run from start to finish](docs/screenshots/tailoring.gif)

A tailoring run, sped up about 2x. Everything in the GIF and screenshots is made-up demo data
(fake companies, a fake student), and the model's replies in the GIF are scripted. The rest is the
real pipeline: quote checks, LaTeX, the one page check and the reviewer.

## What it does

- **Collects postings** from a few dozen public GitHub internship lists and 186 company job boards
  on 12 platforms (Greenhouse, Lever, Ashby, Workday...), on a schedule or when you start a scrape.
- **Filters and dedupes.** It keeps Canadian internships and co-ops, puts the Toronto area first,
  and links copies of the same posting found on several boards.
- **Ranks by fit** with a small local embedding model that also learns from the jobs you save and
  delete.
- **Tracks applications** with a status, notes, follow up dates and an activity page.
- **Tailors documents.** A research step, two writers and a reviewer produce a one page resume and
  a cover letter that only use what's in your profile.
- **Uses the context your resume leaves out.** Every job and project in your profile has a field
  for the details that didn't fit: tools, numbers, decisions. Another AI can write that brag
  sheet for you with [two prompts](backend/docs/brag-sheet-prompts.md): one has a coding agent
  read the project's repository, the other interviews you. The resume writer builds new bullets
  from it and never claims anything the brag sheet lists as not done.
- **Posts to Discord** if you want: a daily message with the new jobs and a scrape health report.

| Workspace                                          | Job calendar                               |
| -------------------------------------------------- | ------------------------------------------ |
| ![Workspace](docs/screenshots/workspace.png)       | ![Job calendar](docs/screenshots/jobs.png) |
| **Job page**                                       | **Your profile**                           |
| ![Job page](docs/screenshots/job-detail.png)       | ![Profile](docs/screenshots/profile.png)   |
| **Application tracker**                            | **Activity**                               |
| ![Applications](docs/screenshots/applications.png) | ![Activity](docs/screenshots/activity.png) |

## Tech stack

| Part         | Built with                                                              |
| ------------ | ----------------------------------------------------------------------- |
| Backend      | Python 3.11+, FastAPI, Pydantic, Playwright (headless Chromium)         |
| Storage      | PostgreSQL 18 with JSONB records                                        |
| Match scores | bge-small-en-v1.5 on ONNX Runtime, optional GPU sidecar on a Jetson     |
| AI           | any OpenAI compatible API (OpenAI, OpenRouter, Ollama, LM Studio)       |
| Documents    | LaTeX compiled with Tectonic, pypdf to read the PDF back                |
| Frontend     | Angular 21, PrimeNG, TypeScript, Vitest                                 |
| Ops          | Docker Compose, nginx, GitHub Actions                                   |

## How it works

The API and the scrape worker are the same Python package started two ways. Every import runs as
its own child process, so one broken source can't take a whole batch down with it.

```mermaid
flowchart LR
    app["Angular app"] -->|/api| web["nginx"]
    web --> api["FastAPI"]
    api -->|manual scrape| importer["importer<br/>one process per source"]
    worker["worker<br/>schedule and match scoring"] -->|scheduled scrape| importer
    importer --> sites["GitHub lists,<br/>job boards"]
    api --> agents["tailoring agents"]
    agents --> llm["any OpenAI compatible API"]
    importer --> db[("PostgreSQL<br/>JSONB records")]
    api --> db
    worker --> db
    worker -.->|optional| gpu["GPU embedder<br/>on a Jetson"]

    classDef ui fill:#eaf1fc,stroke:#345e91,stroke-width:1.5px,color:#345e91
    classDef py fill:#e4f3e8,stroke:#236746,stroke-width:1.5px,color:#236746
    classDef ai fill:#f0ebfa,stroke:#695195,stroke-width:1.5px,color:#695195
    classDef ext fill:#f1efeb,stroke:#66625a,stroke-width:1.5px,color:#66625a
    classDef optional fill:#f1efeb,stroke:#66625a,stroke-width:1.5px,stroke-dasharray:4 3,color:#66625a
    class app,web ui
    class api,worker,importer py
    class agents,llm ai
    class sites,db ext
    class gpu optional
```

### Tailoring

Tailoring is a chain of separate model calls instead of one big prompt. Purple rounded boxes are
model calls. Green boxes are checks in plain Python, not another model call:

```mermaid
flowchart TD
    posting["job posting and<br/>public company pages"] --> research("research<br/>writes a brief that quotes its sources")
    research --> quotes{"every quote found<br/>in its source?"}
    quotes -->|no| you(("you decide"))
    quotes -->|yes| writers
    profile["your profile"] --> writers
    subgraph writers ["run in parallel"]
        resume("resume writer<br/>picks entries from your profile")
        letter("cover letter writer")
    end
    writers --> pdf["LaTeX to a one page PDF,<br/>then read the text back"]
    pdf --> reviewer("reviewer")
    reviewer -.->|one revision| writers
    reviewer -->|looks good| saved[("saved documents")]
    reviewer -->|still has issues| you

    classDef model fill:#f0ebfa,stroke:#695195,stroke-width:1.5px,color:#695195
    classDef check fill:#e4f3e8,stroke:#236746,stroke-width:1.5px,color:#236746
    classDef human fill:#fff2d6,stroke:#876019,stroke-width:1.5px,color:#876019
    classDef data fill:#f1efeb,stroke:#66625a,stroke-width:1.5px,color:#66625a
    class research,resume,letter,reviewer model
    class quotes,pdf check
    class you human
    class posting,profile,saved data
    style writers fill:none,stroke:#8b9a93,stroke-dasharray:5 5
```

The resume writer returns JSON, not prose. It picks experience entries, bullets and skills by index
from the saved profile, so it can't add a job or a skill you don't have. The research quotes are
checked against the fetched pages in plain Python, not by asking the model again.

### Reading a job page

Most posting pages don't need a browser. Each job link tries the cheapest way to read the page
first, and headless Chromium is the last resort. A page the site's robots.txt rules out is never
opened. Blue boxes fetch the page, and amber means you open it yourself.
[docs/how-it-works.md](docs/how-it-works.md#reading-a-job-page) has every check in order:

```mermaid
flowchart TD
    link(["job link"]) --> gate["host skipped<br/>after bot checks?"]
    gate -->|no| cache["page cache"]
    cache -->|miss| robots["robots.txt<br/>allows it?"]
    robots -->|no| flag
    robots -->|yes| api["provider's posting API"]
    api -->|none| http["plain HTTP, paced per host"]
    http -->|cut off| browser["headless Chromium"]
    cache -->|hit| extract(["extract"])
    api -->|found| extract
    http -->|full page| extract
    browser --> extract
    gate -->|yes| later["try again later"]
    http -->|bot check| flag["flag it for<br/>manual review"]

    classDef check fill:#e4f3e8,stroke:#236746,stroke-width:1.5px,color:#236746
    classDef fetch fill:#eaf1fc,stroke:#345e91,stroke-width:1.5px,color:#345e91
    classDef human fill:#fff2d6,stroke:#876019,stroke-width:1.5px,color:#876019
    classDef data fill:#f1efeb,stroke:#66625a,stroke-width:1.5px,color:#66625a
    class gate,robots check
    class cache,api,http,browser fetch
    class flag human
    class link,extract,later data
```

### Match scoring

Jobs are ranked by a small embedding model that runs locally, so scoring costs nothing per job. Raw
similarity rates almost every job as a decent match, so scores become percentiles first. Same colors
as above: purple is the model, green is plain Python and amber is you:

```mermaid
flowchart LR
    jobs["jobs"] --> embed("embed title and description<br/>with bge-small-en-v1.5<br/>on ONNX Runtime")
    profile["your profile and<br/>target roles"] --> vectors("profile vectors")
    feedback["saved, applied and<br/>deleted jobs"] --> vectors
    embed --> similarity["cosine similarity"]
    vectors --> similarity
    similarity --> percentile["percentile across all jobs"]
    percentile --> score["role 40%, background 25%,<br/>skills 20%, location 15%,<br/>plus up to 30% from feedback"]

    classDef model fill:#f0ebfa,stroke:#695195,stroke-width:1.5px,color:#695195
    classDef check fill:#e4f3e8,stroke:#236746,stroke-width:1.5px,color:#236746
    classDef human fill:#fff2d6,stroke:#876019,stroke-width:1.5px,color:#876019
    classDef data fill:#f1efeb,stroke:#66625a,stroke-width:1.5px,color:#66625a
    class embed,vectors model
    class similarity,percentile,score check
    class feedback human
    class jobs,profile data
```

### Deployment

`docker compose up -d --build` in `backend/` starts four containers on one machine, five with the
GPU overlay. The api and the worker run the same image and never call each other: they share
Postgres, and lock files on the data volume let only one scrape batch run at a time. Same colors
as above. Click a diagram for its notes in
[docs/how-it-works.md](docs/how-it-works.md#deployment):

| Containers                                                                     | Components                                                                                |
| ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| [![Containers](docs/diagrams/containers.svg)](docs/how-it-works.md#containers) | [![Components](docs/diagrams/components.svg)](docs/how-it-works.md#components)            |
| **Starting up**                                                                | **The worker loop**                                                                       |
| [![Starting up](docs/diagrams/startup.svg)](docs/how-it-works.md#starting-up)  | [![The worker loop](docs/diagrams/worker-loop.svg)](docs/how-it-works.md#the-worker-loop) |

[docs/how-it-works.md](docs/how-it-works.md) has the rest: the
[states a tailoring run moves through](docs/how-it-works.md#tailoring), what each scrape does and
the data model.

## Running it

You need Docker. Tailoring also needs an OpenAI compatible endpoint (OpenAI, OpenRouter, or a local
Ollama or LM Studio server).

```sh
cd backend
cp .env.example .env     # set JOB_POSTGRES_PASSWORD, and the JOB_AI_ lines for tailoring
docker compose up -d --build
```

Open http://localhost, fill in your profile (or upload a resume) and run a scrape from the
workspace. The worker also scrapes on its own: GitHub lists every 2 hours, job board APIs every 3
hours and career sites at 03:00 and 15:00 ([schedules.json](backend/src/job_backend/scrape/worker/schedules.json)).

If other machines can reach the server, set a sign in password first. Run
`python -m job_backend.auth.hash_password` and paste the printed line into `backend/.env`.

### GPU embeddings (optional)

Match scoring runs on the CPU by default. On an NVIDIA Jetson with JetPack 6 and the nvidia
container runtime, the embedding model can run on the GPU instead:

```sh
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
```

If the GPU sidecar goes down, the worker keeps scoring on the CPU.

### Local development

Backend, Python 3.11 or newer:

```sh
cd backend
python -m venv .venv
source .venv/bin/activate      # windows: .venv\Scripts\activate
python -m pip install -e '.[dev]'
cp .env.example .env
docker compose up -d postgres
python -m uvicorn job_backend.main:app --reload    # api docs at http://localhost:8000/docs
python -m job_backend.scrape.worker                # the scheduler, in another terminal
```

Frontend, Node 24:

```sh
cd frontend
npm ci
npm start    # http://localhost:4200, /api is proxied to localhost:8000
```

PDF export needs [Tectonic](https://tectonic-typesetting.github.io/). You can also scrape a single
source by hand with `python -m job_backend.cli --repo simplify-summer2027` or
`--company 1password`, and `--list-companies` prints every board.

`python scripts/check.py` runs what CI runs: ruff, pyright, pytest, eslint, prettier, the
production build and the frontend tests. The tests run offline and never call a paid API.

## Known limitations

- It's built for Canadian internships, Toronto area first. Other countries would
  need new location rules.
- One user. There's a single profile and an optional password, no accounts.
- Postings that only exist on LinkedIn, Indeed or Glassdoor are missed on purpose.
- A posting whose page is ruled out by the site's robots.txt is flagged for you to open, with only
  the details its list gave.
- Without AI, extraction is rule based and can get unusual postings wrong. AI extraction for
  scrapes is opt in.
- Tailoring makes paid API calls. The app shows the token counts, but read everything it writes
  before you send it.
- The GPU overlay is written for a Jetson. It mounts the host's CUDA and cuDNN libraries, so other
  GPUs need a different compose file.

## Layout

```text
backend/src/job_backend/
  scrape/        github lists, job board adapters, import pipeline, scheduler
  jobs/          saved jobs, browsing, tailoring runs
  resumes/       research, writers, reviewer, latex, pdf checks
  matching/      embedding based match scores
  profile/       your profile
  persistence/   postgres access and migrations
backend/embedder/  optional gpu embedding sidecar
frontend/src/app/  angular app
```

## License

[MIT](LICENSE). Resumes use
[Jake's resume template](backend/src/job_backend/resumes/render_latex/templates/JAKE_TEMPLATE_LICENSE.txt),
also MIT.
