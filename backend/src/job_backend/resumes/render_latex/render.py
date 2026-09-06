import re
import unicodedata
from importlib.resources import files
from urllib.parse import quote, urlsplit

from job_backend.resumes.latex import escape_latex
from job_backend.resumes.models import GeneratedCoverLetter, GeneratedResume, UserResume
from job_backend.resumes.profile_links import profile_label


def resume_to_latex(resume: GeneratedResume | UserResume) -> str:
    fit = isinstance(resume, GeneratedResume)
    lines = [
        r"\begin{center}",
        r"\textbf{\Huge " + escape_latex(resume.name) + r"} \\ \vspace{1pt}",
    ]
    contact = contact_links(resume)
    if contact:
        lines.append(r"\small " + r" $|$ ".join(contact))
    lines.append(r"\end{center}")
    if resume.education:
        lines.extend([r"\section{Education}", r"\resumeSubHeadingListStart"])
        for index, item in enumerate(resume.education):
            # short grade lines get joined onto the degree line
            grades = [bullet for bullet in item.bullets if _GRADE.match(bullet)]
            degree = " in ".join(value for value in [item.degree, item.field_of_study] if value)
            lines.extend(
                [
                    _subheading(
                        item.institution,
                        item.location or "",
                        " | ".join(value.strip() for value in [degree, *grades] if value),
                        _dates(item.start_date, item.end_date),
                    ),
                    *_coursework(item.coursework, f"coursework-{index}" if fit else None),
                    *_bullets([bullet for bullet in item.bullets if bullet not in grades]),
                ]
            )
        lines.append(r"\resumeSubHeadingListEnd")
    if resume.experience:
        lines.extend([r"\section{Experience}", r"\resumeSubHeadingListStart"])
        for index, experience in enumerate(resume.experience):
            lines.extend(
                [
                    _subheading(
                        experience.title,
                        _dates(experience.start_date, experience.end_date),
                        experience.company,
                        experience.location or "",
                    ),
                    *_bullets(experience.bullets, line_id=f"experience-{index}"),
                ]
            )
        lines.append(r"\resumeSubHeadingListEnd")
    if resume.projects:
        lines.extend([r"\section{Projects}", r"\resumeSubHeadingListStart"])
        for index, project in enumerate(resume.projects):
            name = (
                latex_web_link(project.url, project.name)
                if project.url
                else escape_latex(project.name)
            )
            dates = escape_latex(_dates(project.start_date, project.end_date))
            if fit:
                stack = project.technologies
                lines.append(r"\resumeFitHeading{project-" + str(index) + "}{" + dates + "}%")
                lines.extend(
                    _fit_option(count, _project_heading(name, stack[:count]))
                    for count in range(len(stack), 0, -1)
                )
                lines.append(r"\resumeFitLast{0}{" + _project_heading(name, []) + "}%")
                heading = r"\resumeFitted"
            else:
                heading = _project_heading(name, project.technologies)
            lines.append(r"\resumeProjectHeading{" + heading + "}{" + dates + "}")
            lines.extend(_bullets(project.bullets, line_id=f"project-{index}"))
        lines.append(r"\resumeSubHeadingListEnd")
    lines.extend(_skills(resume))
    for section in resume.additional_sections:
        lines.append(r"\section{" + _heading(section.title) + "}")
        lines.extend(_bullets(section.items))
    template = (
        files("job_backend.resumes.render_latex")
        .joinpath("templates/jakes_resume.tex")
        .read_text(encoding="utf-8")
    )
    return template.replace("%%RESUME_BODY%%", "\n".join(lines))


_GRADE = re.compile(r"^\s*(c?gpa|grade|average|cumulative)\b.{0,40}$", re.IGNORECASE)


def _skills(resume: GeneratedResume | UserResume) -> list[str]:
    groups = [group for group in resume.skills if group.items]
    if not groups:
        return []
    skill_lines = [
        r"\textbf{" + escape_latex(group.category) + ":} " + escape_latex(", ".join(group.items))
        for group in groups
    ]
    return [
        r"\section{Technical Skills}",
        r"\begin{itemize}[leftmargin=0.15in, label={}]",
        r"\small{\item{",
        r" \\".join(skill_lines),
        r"}}",
        r"\end{itemize}",
    ]


def _project_heading(name: str, technologies: list[str]) -> str:
    heading = r"\textbf{" + name + "}"
    if technologies:
        heading += r" $|$ \emph{" + escape_latex(", ".join(technologies)) + "}"
    return heading


def _fit_option(count: int, content: str) -> str:
    return r"\resumeFitOption{" + str(count) + "}{" + content + "}%"


def _coursework(courses: list[str], fit_id: str | None) -> list[str]:
    if not courses:
        return []
    if fit_id is None:
        return [r"\resumeCoursework{" + escape_latex(", ".join(courses)) + "}"]
    width = r"\dimexpr\linewidth-2pt\relax"
    prefix = r"\textbf{Relevant Coursework:} "
    return [
        r"\resumeFitStart{" + fit_id + "}{" + width + "}{" + prefix + "}%",
        *(
            _fit_option(count, escape_latex(", ".join(courses[:count])))
            for count in range(len(courses), 1, -1)
        ),
        r"\resumeFitLast{1}{" + escape_latex(courses[0]) + "}%",
        r"\resumeCoursework{\resumeFitted}",
    ]


def _heading(title: str) -> str:
    accents = {"\u0300": "`", "\u0301": "'", "\u0302": "^", "\u0308": '"', "\u0303": "~"}
    output: list[str] = []
    for char in unicodedata.normalize("NFD", title):
        if char in accents and output:
            output[-1] = "\\" + accents[char] + "{" + output[-1] + "}"
        elif not unicodedata.combining(char):
            output.append(escape_latex(char))
    return "".join(output)


def _dates(start: str | None, end: str | None) -> str:
    return " -- ".join(value for value in [start, end] if value)


def _subheading(left: str, right: str, second_left: str, second_right: str) -> str:
    return r"\resumeSubheading" + "".join(
        "{" + escape_latex(value) + "}" for value in [left, right, second_left, second_right]
    )


def contact_links(document: GeneratedResume | UserResume | GeneratedCoverLetter) -> list[str]:
    contact: list[str] = []
    if document.phone:
        contact.append(latex_href("tel:" + re.sub(r"[^+0-9]", "", document.phone), document.phone))
    if document.location:
        contact.append(escape_latex(document.location))
    if document.email:
        contact.append(latex_href("mailto:" + quote(document.email, safe="@.+-"), document.email))
    if document.linkedin:
        label = document.linkedin_label or profile_label(document.linkedin)
        contact.append(latex_href(document.linkedin, label))
    if document.github:
        contact.append(latex_href(document.github, profile_label(document.github)))
    contact.extend(latex_web_link(link) for link in document.links)
    return contact


def latex_href(url: str, label: str) -> str:
    return r"\href{" + escape_latex(url) + r"}{\underline{" + escape_latex(label) + "}}"


def latex_web_link(url: str, label: str | None = None) -> str:
    destination = url.strip()
    try:
        parts = urlsplit(destination)
        if not parts.scheme and not destination.startswith("/"):
            destination = "https://" + destination
            parts = urlsplit(destination)
        valid = (
            parts.scheme in {"http", "https"}
            and bool(parts.hostname and "." in parts.hostname)
            and not parts.username
            and not parts.password
            and not re.search(r"[\s\\]", destination)
        )
        # reading .port also catches bad ports
        _ = parts.port
    except ValueError:
        return escape_latex(label or url)
    if not valid:
        return escape_latex(label or url)
    if label is None:
        if parts.hostname in {"linkedin.com", "www.linkedin.com"}:
            label = "LinkedIn"
        elif parts.hostname in {"github.com", "www.github.com"}:
            label = "GitHub"
    return latex_href(destination, label or url)


_METRIC = re.compile(
    r"(?<![\w.,/-])\$?\d+(?:[.,]\d+)*(?:ms|s|x|KB|MB|GB|TB|[kKMB])?\+?%?(?![A-Za-z0-9])"
)


def first_metric(text: str) -> re.Match[str] | None:
    return _METRIC.search(text)


def _bullets(items: list[str], *, line_id: str | None = None) -> list[str]:
    if not items:
        return []
    return [
        r"\resumeItemListStart",
        *(
            r"\resumeItem{" + escape_latex(item) + "}"
            if line_id is None
            else _measured_bullet(f"{line_id}-{number}", item)
            for number, item in enumerate(items)
        ),
        r"\resumeItemListEnd",
    ]


def _measured_bullet(line_id: str, text: str) -> str:
    metric = first_metric(text)
    split = 0 if metric is None else metric.end()
    lead, rest = escape_latex(text[:split]), escape_latex(text[split:])
    return r"\resumeLineItem{" + line_id + "}{" + lead + "}{" + rest + "}"
