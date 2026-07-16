from job_backend.profile.tailoring import candidate_evidence, tailoring_source
from job_backend.resumes.compile_pdf.models import CompiledPdf
from job_backend.resumes.models import UserResume
from job_backend.resumes.preview.preview import preview_resume
from tests.resumes.helpers import resume
from tests.resumes.pdf_helpers import pdf_bytes


def with_switched_off_project() -> UserResume:
    source = resume().model_dump()
    source["projects"].append(
        {
            **source["projects"][0],
            "name": "Intern Radar",
            "bullets": ["Built Intern Radar."],
            "raw_description": "Intern Radar crawled 40 job boards.",
            "enabled": False,
        }
    )
    return UserResume.model_validate(source)


def test_disabled_entries_left_out() -> None:
    source = with_switched_off_project()
    before = source.model_dump_json()
    assert [project.name for project in tailoring_source(source).projects] == ["Search_Project"]
    assert "40 job boards" not in candidate_evidence(source)
    printed: list[str] = []

    def compiler(latex: str) -> CompiledPdf:
        printed.append(latex)
        return CompiledPdf(pdf_bytes(1), "")

    preview_resume(source, compiler=compiler)
    assert r"Search\_Project" in printed[0]
    assert "Intern Radar" not in printed[0]
    assert source.model_dump_json() == before
