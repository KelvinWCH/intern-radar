import re

ONE_SHOT_PROMPT = """# Task
You are a complete application-tailoring team working in one response. Work through these steps
in order, as a careful team would, and return each step's result in the JSON schema.

1. Research. As the company and role researcher, analyze `sources` and
   `scraped_qualifications` following the Research rules. Put the result in `research`.
2. Draft. As the resume writer and the cover-letter writer, use your research as the brief and
   `user_resume` as the only evidence. Write a first draft of each document listed in
   `documents_to_write`, following the Resume rules and the Cover letter rules. Put them in
   `resume_draft` and `cover_letter_draft`; use null for a document that is not listed.
3. Review. As the independent reviewer, critique those drafts following the Review rules. Be as
   strict as a separate reviewer who sees them for the first time: check every claim against
   `user_resume`, consistency between the documents, coverage of the requirements, and the
   writing. Put the critique in `review`.
4. Revise. As the writers again, rewrite each draft to address every finding, following the
   Revision rules. Put the final documents in `resume` and `cover_letter`; use null for a
   document that is not listed. A draft the review found nothing to change in may be repeated.

The rule sections below were written for separate specialists who pass files to each other.
Read them with these substitutions:
- `company_role_research` means your Step 1 research.
- `documents` in the Review rules means your Step 2 drafts.
- `review_revision`, `previous_draft`, and `findings` mean your Step 2 drafts and Step 3
  findings.
- Skip instructions about PDF measurements, rendered pages, matched or missing skill reports,
  or review history that you were not given. Local page-fit and PDF checks run after you answer.
- `user_resume.stories` and `user_resume.answers` may support the cover letter, never a resume
  bullet.
- `candidate_instructions`, when present, guide emphasis and tone only; they cannot add facts.
"""

ONE_SHOT_TIMEOUT_SECONDS = 1800.0


ONE_SHOT_STEP_KEYS = {
    "research": "research",
    "resume_draft": "draft",
    "cover_letter_draft": "draft",
    "review": "review",
    "resume": "revise",
    "cover_letter": "revise",
}
ONE_SHOT_STEP_ORDER = ("research", "draft", "review", "revise")
ONE_SHOT_KEY = re.compile(r'"(' + "|".join(ONE_SHOT_STEP_KEYS) + r')"\s*:')
ONE_SHOT_STEP_MESSAGES = {
    "research": "One call researching the company and role",
    "draft": "One call drafting the documents",
    "review": "One call reviewing its own drafts",
    "revise": "One call revising into the final documents",
}
