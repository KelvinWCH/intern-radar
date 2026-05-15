from job_backend.scrape.github.github_sources.bobwillrule_canada import (
    ADAPTER as bobwillrule_canada,
)
from job_backend.scrape.github.github_sources.emjumaev_internships import (
    ADAPTER as emjumaev_internships,
)
from job_backend.scrape.github.github_sources.evan_toronto import ADAPTER as evan_toronto
from job_backend.scrape.github.github_sources.firstjobby_internships import (
    ADAPTER as firstjobby_internships,
)
from job_backend.scrape.github.github_sources.francklin_canada import ADAPTER as francklin_canada
from job_backend.scrape.github.github_sources.frogg_canada import ADAPTER as frogg_canada
from job_backend.scrape.github.github_sources.hanson_canada import ADAPTER as hanson_canada
from job_backend.scrape.github.github_sources.internatlas import ADAPTER as internatlas
from job_backend.scrape.github.github_sources.jobright_accounting import (
    ADAPTER as jobright_accounting,
)
from job_backend.scrape.github.github_sources.jobright_art import ADAPTER as jobright_art
from job_backend.scrape.github.github_sources.jobright_business import ADAPTER as jobright_business
from job_backend.scrape.github.github_sources.jobright_consulting import (
    ADAPTER as jobright_consulting,
)
from job_backend.scrape.github.github_sources.jobright_data import ADAPTER as jobright_data
from job_backend.scrape.github.github_sources.jobright_design import ADAPTER as jobright_design
from job_backend.scrape.github.github_sources.jobright_education import (
    ADAPTER as jobright_education,
)
from job_backend.scrape.github.github_sources.jobright_engineering import (
    ADAPTER as jobright_engineering,
)
from job_backend.scrape.github.github_sources.jobright_hr import ADAPTER as jobright_hr
from job_backend.scrape.github.github_sources.jobright_legal import ADAPTER as jobright_legal
from job_backend.scrape.github.github_sources.jobright_management import (
    ADAPTER as jobright_management,
)
from job_backend.scrape.github.github_sources.jobright_marketing import (
    ADAPTER as jobright_marketing,
)
from job_backend.scrape.github.github_sources.jobright_product import ADAPTER as jobright_product
from job_backend.scrape.github.github_sources.jobright_public_sector import (
    ADAPTER as jobright_public_sector,
)
from job_backend.scrape.github.github_sources.jobright_sales import ADAPTER as jobright_sales
from job_backend.scrape.github.github_sources.jobright_software import ADAPTER as jobright_software
from job_backend.scrape.github.github_sources.jobright_support import ADAPTER as jobright_support
from job_backend.scrape.github.github_sources.michelle_canada import ADAPTER as michelle_canada
from job_backend.scrape.github.github_sources.negar_canada import ADAPTER as negar_canada
from job_backend.scrape.github.github_sources.north_america_internships import (
    ADAPTER as north_america_internships,
)
from job_backend.scrape.github.github_sources.northwestern_quant import (
    ADAPTER as northwestern_quant,
)
from job_backend.scrape.github.github_sources.resumax_internships import (
    ADAPTER as resumax_internships,
)
from job_backend.scrape.github.github_sources.ricsign_internships import (
    ADAPTER as ricsign_internships,
)
from job_backend.scrape.github.github_sources.simplify_internships import (
    ADAPTER as simplify_internships,
)
from job_backend.scrape.github.github_sources.speedyapply_ai import ADAPTER as speedyapply_ai
from job_backend.scrape.github.github_sources.speedyapply_swe import ADAPTER as speedyapply_swe
from job_backend.scrape.github.github_sources.surya_internships import ADAPTER as surya_internships
from job_backend.scrape.github.github_sources.understudy_internships import (
    ADAPTER as understudy_internships,
)
from job_backend.scrape.github.github_sources.vansh_internships import ADAPTER as vansh_internships
from job_backend.scrape.github.github_sources.won_internships import ADAPTERS as won_internships
from job_backend.scrape.github.github_sources.zapply_canada import ADAPTER as zapply_canada
from job_backend.scrape.pipeline.models import JobSource

DEFAULT_REPOSITORY = simplify_internships.name
REPOSITORIES: dict[str, JobSource] = {
    board.name: board
    for board in (
        simplify_internships,
        speedyapply_swe,
        speedyapply_ai,
        northwestern_quant,
        frogg_canada,
        zapply_canada,
        bobwillrule_canada,
        emjumaev_internships,
        michelle_canada,
        negar_canada,
        vansh_internships,
        understudy_internships,
        north_america_internships,
        resumax_internships,
        firstjobby_internships,
        francklin_canada,
        hanson_canada,
        evan_toronto,
        surya_internships,
        internatlas,
        ricsign_internships,
        jobright_product,
        jobright_management,
        jobright_engineering,
        jobright_design,
        jobright_sales,
        jobright_accounting,
        jobright_art,
        jobright_legal,
        jobright_hr,
        jobright_public_sector,
        jobright_education,
        jobright_support,
        jobright_marketing,
        jobright_software,
        jobright_data,
        jobright_business,
        jobright_consulting,
        *won_internships,
    )
}
