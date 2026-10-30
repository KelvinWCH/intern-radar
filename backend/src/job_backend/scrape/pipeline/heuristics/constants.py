import re

INTERNSHIP_EMPLOYMENT_TYPES = frozenset({"intern", "internship", "internships", "co op", "coop"})


GTA_LOCATIONS = (
    "toronto",
    "markham",
    "mississauga",
    "brampton",
    "vaughan",
    "richmond hill",
    "oakville",
    "scarborough",
    "north york",
    "pickering",
    "ajax",
    "whitby",
    "oshawa",
    "greater toronto",
    "gta",
    "etobicoke",
    "newmarket",
    "aurora",
    "burlington",
)

CANADIAN_LOCATIONS = (
    "canada",
    "canadian",
    "ontario",
    "quebec",
    "british columbia",
    "alberta",
    "manitoba",
    "saskatchewan",
    "nova scotia",
    "new brunswick",
    "newfoundland",
    "labrador",
    "prince edward island",
    "yukon",
    "nunavut",
    "northwest territories",
    "vancouver",
    "montreal",
    "ottawa",
    "waterloo",
    "kitchener",
    "calgary",
    "edmonton",
    "winnipeg",
    "halifax",
    "saskatoon",
    "regina",
    "fredericton",
    "burnaby",
    "surrey",
    "guelph",
    "kelowna",
    "laval",
    "gatineau",
    "sherbrooke",
    "moncton",
    "st johns",
)

PROVINCE_PATTERN = re.compile(r"(?:,|\s[-/]\s)\s*(ON|BC|QC|AB|MB|SK|NS|NB|NL|PE|NT|NU|YT)\b", re.I)

FOREIGN_LOCATION_PATTERN = re.compile(
    r"\b(united states|usa|united kingdom|uk|england|australia|india|germany|france)\b"
    r"|,\s*(?:US|OH|TX|WA|IL|NY|MA|FL|PA|MI)\b",
    re.I,
)


TITLE_FIELDS = ("title", "text", "jobTitle", "job_title", "requisitionTitle", "name")
LOCATION_FIELDS = (
    "locations",
    "location",
    "locationsText",
    "secondaryLocations",
    "additionalLocations",
    "jobLocation",
    "applicantLocationRequirements",
    "country",
    "countryCode",
    "country_code",
    "requisitionLocations",
)
EMPLOYMENT_FIELDS = (
    "employmentType",
    "employment_type",
    "commitment",
    "jobType",
    "workerSubType",
    "efcustomTextEmploymentType",
)
NON_STUDENT_TITLE = re.compile(
    r"\b(senior|sr|staff|principal|director|head|vice president|manager|new grad|new graduate|"
    r"postdoc|postdoctoral|professor|faculty)\b",
    re.I,
)
FOREIGN_LOCATION = re.compile(
    r"\b(united states|usa|united kingdom|uk|england|australia|india|germany|france|"
    r"switzerland|hungary|poland|netherlands|ireland|spain|italy|china|japan|taiwan|"
    r"israel|singapore|mexico|brazil|romania|czechia|sweden|denmark|finland|korea|"
    r"vietnam|philippines|portugal|austria|belgium|new zealand)\b|"
    r"(?:^|[,;/]\s*)(?:US|USA|GB|GBR|DE|IND|AUS)(?:\s*[,;/]|$)|"
    r",\s*(?:OH|TX|WA|IL|NY|MA|FL|PA|MI|CA)\b",
    re.I,
)
