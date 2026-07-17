from job_backend.matching.skills import SkillMatcher


def test_skill_aliases() -> None:
    matcher = SkillMatcher(["PostgreSQL", "JavaScript", "C++", "C#", "C", "Node.js"])
    found = matcher.find("We use Postgres, JS, C++ and NodeJS; C# is a plus.")
    assert found == {"PostgreSQL", "JavaScript", "C++", "C#", "Node.js"}
    assert matcher.find("Strong C programming") == {"C"}
