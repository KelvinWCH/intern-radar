SKILL_ALIASES: dict[str, tuple[str, ...]] = {
    "Python": ("Python",),
    "Java": ("Java",),
    "JavaScript": ("JavaScript", "JS"),
    "TypeScript": ("TypeScript", "TS"),
    "C": ("C",),
    "C++": ("C++", "C plus plus"),
    "C#": ("C#", "C sharp"),
    "Go": ("Golang", "Go programming"),
    "Rust": ("Rust",),
    "Ruby": ("Ruby",),
    "PHP": ("PHP",),
    "Swift": ("Swift",),
    "Kotlin": ("Kotlin",),
    "Scala": ("Scala",),
    "SQL": ("SQL", "Structured Query Language"),
    "HTML": ("HTML", "HTML5"),
    "CSS": ("CSS", "CSS3"),
    "React": ("React", "React.js", "ReactJS"),
    "Angular": ("Angular",),
    "AngularJS": ("AngularJS",),
    "Vue.js": ("Vue.js", "VueJS", "Vue"),
    "Node.js": ("Node.js", "NodeJS", "Node JS"),
    "Next.js": ("Next.js", "NextJS"),
    "Django": ("Django",),
    "Flask": ("Flask",),
    "FastAPI": ("FastAPI",),
    "Spring Boot": ("Spring Boot",),
    ".NET": (".NET", "dotnet"),
    "PostgreSQL": ("PostgreSQL", "Postgres"),
    "MySQL": ("MySQL",),
    "MongoDB": ("MongoDB", "Mongo DB"),
    "Redis": ("Redis",),
    "Git": ("Git",),
    "GitHub": ("GitHub",),
    "GitLab": ("GitLab",),
    "Docker": ("Docker",),
    "Kubernetes": ("Kubernetes", "K8s"),
    "Terraform": ("Terraform",),
    "Linux": ("Linux",),
    "Unix": ("Unix",),
    "AWS": ("AWS", "Amazon Web Services"),
    "Azure": ("Azure", "Microsoft Azure"),
    "Google Cloud": ("Google Cloud", "Google Cloud Platform", "GCP"),
    "Power BI": ("Power BI", "PowerBI"),
    "Tableau": ("Tableau",),
    "Excel": ("Excel", "Microsoft Excel"),
    "PowerPoint": ("PowerPoint", "Microsoft PowerPoint"),
    "Figma": ("Figma",),
    "Jira": ("Jira",),
    "Salesforce": ("Salesforce",),
    "TensorFlow": ("TensorFlow",),
    "PyTorch": ("PyTorch",),
    "Pandas": ("Pandas",),
    "NumPy": ("NumPy",),
    "Spark": ("Spark", "Apache Spark", "PySpark"),
    "Machine learning": ("machine learning",),
    "Data analysis": ("data analysis", "data analytics"),
    "Data visualization": ("data visualization", "data visualisation"),
    "Unit testing": ("unit testing", "unit tests"),
    "Version control": ("version control",),
    "Project management": ("project management",),
    "Communication": ("communication", "communication skills", "written and verbal communication"),
    "Problem solving": ("problem solving", "problem-solving"),
    "Teamwork": ("teamwork", "team collaboration"),
    "Customer service": ("customer service",),
}

UMBRELLA_TERMS: dict[str, tuple[str, ...]] = {
    "ci/cd": (
        "continuous integration",
        "continuous delivery",
        "continuous deployment",
        "GitHub Actions",
        "GitLab CI",
        "Jenkins",
        "CircleCI",
    ),
    "automated testing": (
        "unit tests",
        "unit testing",
        "integration tests",
        "end-to-end tests",
        "pytest",
        "JUnit",
        "Jest",
        "Cypress",
        "Playwright",
        "Selenium",
    ),
    "version control": ("Git",),
    "containerization": ("Docker", "Kubernetes"),
    "containers": ("Docker", "Kubernetes"),
    "cloud": ("AWS", "Azure", "GCP", "Google Cloud"),
    "relational databases": ("PostgreSQL", "MySQL", "SQL Server", "SQLite", "Oracle"),
    "nosql": ("MongoDB", "DynamoDB", "Firestore", "Cassandra", "Redis"),
}

REQUIRED_HEADING = (
    r"(?:required(?:\s+(?:qualifications|skills|experience|requirements))?"
    r"|(?:minimum|basic|essential)\s+(?:qualifications|requirements|skills)"
    r"|requirements|qualifications|must[- ]have(?:\s+skills)?"
    r"|what\s+you(?:'ll|\s+will)?\s+bring"
    r"|what\s+we(?:'re|\s+are)\s+looking\s+for)"
)

EXCLUDED_HEADING = (
    r"(?:(?:preferred|desired|additional|bonus|optional)\s*(?:qualifications|skills|experience)?"
    r"|nice[- ]to[- ]haves?|(?:key\s+)?responsibilities|duties(?:\s+and\s+responsibilities)?"
    r"|your\s+(?:responsibilities|impact|role)"
    r"|what\s+you(?:'ll|\s+will)\s+(?:do|be\s+doing|get)"
    r"|what\s+we\s+(?:offer|provide)|benefits|perks|compensation"
    r"|about(?:\s+(?:us|the\s+(?:company|team|role)))?|our\s+(?:mission|team|culture)"
    r"|why\s+(?:join|work\s+with)\s+us|equal\s+opportunity(?:\s+employer)?)"
)

OPTIONAL_CLAUSE = (
    r"\b(?:prefer(?:red|ably)?|optional|desirable|beneficial|bonus|nice[- ]to[- ]have|"
    r"not\s+(?:strictly\s+)?(?:required|necessary|essential|mandatory|needed|expected)|"
    r"no\s+.+?\s+(?:required|necessary)|"
    r"an?\s+(?:asset|plus|advantage))\b"
)

ALTERNATIVE_CLAUSE = r"\b(?:or|either|one\s+of|such\s+as|for\s+example)\b|\be\.g\.|/"

MANDATORY_CLAUSE = (
    r"\b(?:you|candidates?|applicants?)\s+(?:must|need\s+to|are\s+required\s+to)\b"
    r"|\bmust\s+(?:have|know|possess|demonstrate|be\s+proficient)\b"
    r"|\bwe\s+require\b|\b(?:is|are)\s+(?:required|mandatory|essential)\b"
)
