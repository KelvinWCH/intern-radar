from importlib.resources import files

from job_backend.resumes.latex import escape_latex
from job_backend.resumes.models import GeneratedCoverLetter
from job_backend.resumes.render_latex.render import contact_links


def cover_letter_to_latex(letter: GeneratedCoverLetter) -> str:
    contact = contact_links(letter)
    lines = [
        r"\begin{center}",
        r"\makebox[\textwidth]{\begin{minipage}{\dimexpr\textwidth+1in\relax}\centering",
        r"{\LARGE\bfseries " + escape_latex(letter.name) + r"\par}",
    ]
    if contact:
        lines.extend(
            [
                r"\smallskip",
                r"{\small " + r" $|$ ".join(contact) + r"\par}",
            ]
        )
    lines.extend(
        [
            r"\end{minipage}}",
            r"\end{center}",
            r"\noindent\rule{\textwidth}{0.4pt}\par",
            r"\textbf{" + escape_latex(letter.company) + r"}\par",
            r"Re: " + escape_latex(letter.job_title) + r"\par",
            escape_latex(letter.greeting) + r"\par",
            *(escape_latex(paragraph) + r"\par" for paragraph in letter.paragraphs),
            r"\noindent\rule{\textwidth}{0.4pt}\par",
            escape_latex(letter.closing) + r"\par\vspace{0.3em}",
            escape_latex(letter.name),
        ]
    )
    template = (
        files("job_backend.resumes.render_cover_letter")
        .joinpath("templates/cover_letter.tex")
        .read_text(encoding="utf-8")
    )
    return template.replace("%%LETTER_BODY%%", "\n".join(lines))
