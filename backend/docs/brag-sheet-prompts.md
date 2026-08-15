# Brag sheet prompts

A resume only has room for a few bullets per job, so most of what you did gets left out. A brag
sheet is the long version: what you built, how you built it and the numbers behind it, written
as plain text. Paste it into an experience's or project's **Context for tailoring** field on the
Profile page, and the resume writer can build new bullets from it when a posting calls for them
(see "Brag sheets" in `generate_resume/constants.py`).

Writing one by hand is tedious, so here are two prompts that get another AI to do it with you:

- **From a repository**, for a coding agent that can read the project's code and commit history.
- **From an interview**, for any chat AI. It asks you a few questions at a time, then writes the
  brag sheet plus a few STAR stories for the Stories section of your profile.

When you get one back, you can also:

- paste its TOOLS lines into the matching inventory's Add box (comma-separated lists work),
- copy its SUGGESTED RESUME BULLETS into Resume bullet points if you want them as your defaults,
- copy each STORY's labeled lines into a new story.

Leave the headings in capitals as they are. The tailor looks for them.

---

## Prompt 1: From a repository

```text
Hi! I'm updating my resume and I'd like your help writing a brag sheet for this project: what I
built, how I built it, and the numbers that back it up. You can read the whole repository, so
please only write down things you can actually see in it, or that I tell you. The format I need
is at the bottom.

Here's how I'd go about it:

1. Start with the README, any docs or notes (DEV_NOTES, CHANGELOG, context.md and so on), the
   package manifests, CI workflows, tests, benchmarks and scripts.
2. Then read the whole commit history, message bodies included:
     git log --no-merges --date=short --format='%h %ad %an%n%B'
   I often put measurements in commit messages. When you find one, copy it exactly, with its
   units, what it was compared against and how it was measured. If other people committed too,
   ask me which author is me before you credit anything to me.
3. For each piece of work worth mentioning, figure out what changed, how it was done, how big it
   was, why it mattered, and where the proof is (a commit hash or a file path).
4. Lean toward the technically interesting work (architecture, algorithms, caching,
   concurrency, data modeling, tracking down a root cause) over routine chores.
5. Keep my work apart from the team's, prototypes apart from what shipped, and plans apart from
   what's done.
6. When you've been through everything, ask me up to 5 short questions in one message, only
   about things the repo can't tell you: who uses it and why, real outcomes (users, money, time
   saved, adoption), how much of it I owned, the team size, and dates. Then wait for my answers.
   Anything I don't know, write "unknown".
7. Give me the finished brag sheet in a single plain-text code block, with nothing after it.

Some ground rules, since this goes on a real resume:

- Please don't invent or guess numbers, users, outcomes or tools. Copy numbers exactly.
- Result is just the outcome. How it was tested (CPU or network throttling, device, lab or field
  data, number of runs, sample size) goes under MEASUREMENT NOTES, tied to its accomplishment.
- Only give a percentage if you worked it out from a before and after value you found. Round it
  down to a whole number and keep the before and after next to it.
- "Why it mattered" is the purpose, user or consumer that the repo or my answers back up. Don't
  say something happened downstream (a launch, revenue, a ranking) unless it's written down
  somewhere.
- If a result came from fixing a misconfiguration or an earlier mistake, that's fine, just say so
  plainly, as a diagnosis: "found X caused Y, fixed it".
- List 6 to 12 accomplishments, best first, one per line, each one making sense on its own.
- TOOLS only lists tools the project actually uses (manifests, imports, CI, scripts), not ones
  that are only mentioned.
- Each suggested resume bullet is either one line of 90 to 105 characters, or two lines of 150 to
  200 characters in total, spaces included. Open with an action verb and the result in words a
  non-technical recruiter would understand, within the first 90 characters, with the technical
  term in brackets, like "Cut mobile load time 62% (LCP)". Then the one strongest method, then
  the scope or purpose, which can go on the second line. Stick to one number or one before and
  after pair. Skip "helped", "worked on", "responsible for" and "leveraged".

The format:

BRAG SHEET
Kind: project
Name:
Organization:
My role:
Dates:
Purpose:
Organization goal (background, not my accomplishment):
Scale:

ACCOMPLISHMENTS
A1. Result: ... | Method: ... | Scope: ... | Why it mattered: ... | Evidence: ...
A2. ...

DECISIONS AND TRADEOFFS
D1. Chose ... over ... because ...; effect: ...

CHALLENGES
C1. ...

MEASUREMENT NOTES
M1 (A1): ...

TOOLS
Languages: comma-separated
Technologies: comma-separated

NOT CLAIMED
- Anything planned, prototype-only, team-owned, unverified, or explicitly not done.

SUGGESTED RESUME BULLETS
- ...
```

---

## Prompt 2: From an interview (with STAR stories)

```text
Hi! Could you interview me about one job, internship, club role or project, so I can get it onto
my resume properly? At the end I'd like a brag sheet and two or three STAR stories, in the
formats at the bottom.

How I'd like the interview to go:

- Ask me 2 to 4 short questions at a time, then wait for my answers. About 4 rounds should do
  it. You can stop once you know the result, how it was measured, how I did it, how big it was
  and why it mattered for at least 4 accomplishments.
- Round 1: the organization and what it does, my team and what it was trying to do, my title,
  my dates, and what I owned versus what the team owned.
- Round 2: ask me for the 3 to 6 things I'm proudest of. For each one, ask what changed, how it
  was measured (before and after, units, lab or production, sample size) and who it helped.
- Round 3: dig into the best ones: why I went that way, what else I considered, the hardest
  part, and the scale (users, records, requests, money, team size).
- Round 4: the tools and skills I really used, what I learned, and anything that was only
  planned, a prototype, or somebody else's work.
- If I'm vague ("improved performance"), ask one follow-up to get the concrete change. If I don't
  have an exact number, ask for a count or a range I could defend in an interview. Please don't
  make one up; write "unknown" instead.

Some ground rules, since this goes on a real resume:

- Please don't invent or guess numbers, users, outcomes or tools. Copy my numbers exactly.
- Result is just the outcome. How it was tested (throttling, device, lab or field data, sample
  size) goes under MEASUREMENT NOTES, tied to its accomplishment.
- Only give a percentage if you worked it out from a before and after value I gave you. Round it
  down to a whole number and keep the before and after next to it.
- "Organization goal" is background. Only credit me with what I did myself.
- If a result came from fixing a misconfiguration or an earlier mistake, that's fine, just say so
  plainly, as a diagnosis: "found X caused Y, fixed it".
- Each suggested resume bullet is either one line of 90 to 105 characters, or two lines of 150 to
  200 characters in total, spaces included. Open with an action verb and the result in words a
  non-technical recruiter would understand, within the first 90 characters, with the technical
  term in brackets. Then the one strongest method, then the scope or purpose, which can go on
  the second line. Stick to one number or one before and after pair. Skip "helped", "worked on",
  "responsible for" and "leveraged".
- STAR stories are for behavioral interviews. Each one is a single, concrete situation, told
  with my own facts, with a measurable result if I gave you one.

When we're done, put the brag sheet in one plain-text code block and the stories in a second
one, and nothing else.

The formats:

BRAG SHEET
Kind: experience
Name: <title> at <organization>
Organization:
My role:
Dates:
Purpose:
Organization goal (background, not my accomplishment):
Scale:

ACCOMPLISHMENTS
A1. Result: ... | Method: ... | Scope: ... | Why it mattered: ... | Evidence: ...

DECISIONS AND TRADEOFFS
D1. Chose ... over ... because ...; effect: ...

CHALLENGES
C1. ...

MEASUREMENT NOTES
M1 (A1): ...

TOOLS
Languages: comma-separated
Technologies: comma-separated

NOT CLAIMED
- Anything planned, prototype-only, team-owned, unverified, or explicitly not done.

SUGGESTED RESUME BULLETS
- ...

STORY
Title:
Related experience:
Situation:
Task:
Action:
Result:
Learning:
Skills: comma-separated
Evidence:
```
