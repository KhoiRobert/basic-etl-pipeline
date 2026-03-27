"""Map free-text job titles to a small set of role categories for grouping."""

from __future__ import annotations

import re

import pandas as pd
from pandas.api.types import is_scalar

# Longer / more specific phrases first within each category where order matters.
# First matching category wins (list order is priority).
_RULES: list[tuple[str, tuple[str, ...]]] = [
        (
        "Project & Product Management",
        (
            "project manager",
            "product owner",
            "product manager",
            "scrum master",
            "quản lý dự án",
            "it project manager",
            "product lead",
            "agile coach",
            "it manager",
            "technical service manager",
            "delivery manager",
        ),
    ),
    (
        "DevOps & Cloud",
        (
            "devops",
            "sre",
            "site reliability",
            "kubernetes",
            "k8s",
            "infrastructure engineer",
            "cloud engineer",
            "ci/cd",
            "system engineer",
            "systems engineer",
            "kỹ thuật hệ thống",
            "it infra",
            " infra ",
            "infra lead",
            "system admin",
            "vận hành cloud",
            "cloud operations",
        ),
    ),
    (
        "Data & Analytics",
        (
            "data engineer",
            "data scientist",
            "data analyst",
            "business intelligence",
            "bi developer",
            "data science",
            "machine learning",
            "ml engineer",
            "ai engineer",
            "deep learning",
            "big data",
            "data admin",
            " chuyên viên bi",
            " cao cấp bi",
            " BI ",
            " BI)",
        ),
    ),
        (
        "Business Analysis",
        (
            "business analyst",
            "business analysis",
            "business analyses",
            "chuyên viên phân tích nghiệp vụ",
            "functional analyst",
            "system analyst",
            "brse",
        ),
    ),
    (
        "QA & Testing",
        (
            "quality assurance",
            "test automation",
            "automation test",
            "manual test",
            "kiểm thử",
            "tester",
            "testing engineer",
            "qa engineer",
            "qa ",
            " qa",
            "qc engineer",
            "quality engineer",
            "software test",
            "kiểm định",
            "pqa",
            "kiểm soát quy trình",
            "quản lý chất lượng",
            "quality management",
        ),
    ),
        (
        "Security",
        (
            "security engineer",
            "security architect",
            "security solution",
            "cybersecurity",
            "cyber security",
            "an ninh mạng",
            "bảo mật thông tin",
            "pentest",
            "penetration",
        ),
    ),
    (
        "Design & UX",
        (
            "ui/ux",
            "ux designer",
            "ui designer",
            "graphic design",
            "designer",
            "thiết kế",
            "ux/",
            "ui/",
        ),
    ),
        (
        "Marketing & Content",
        (
            "marketing",
            "digital marketing",
            "seo",
            "content marketing",
            "content writer",
            "growth hacker",
        ),
    ),
    (
        "Sales & Business Development",
        (
            "business development",
            "account manager",
            "sales executive",
            "kinh doanh",
            "telesales",
        ),
    ),
    (
        "Network & Infrastructure",
        (
            "network engineer",
            "network administrator",
            "network admin",
            "quản trị mạng",
            "kỹ thuật mạng",
            "system network",
            "database administrator",
            "database admin",
            "dba",
            "sysadmin",
            "system administrator",
        ),
    ),
    (
        "Software Development",
        (
            "software engineer",
            "tech lead",
            "technical lead",
            "team lead",
            "lead developer",
            "fullstack",
            "full-stack",
            "full stack",
            "backend",
            "front-end",
            "frontend",
            "front end",
            "web developer",
            "mobile developer",
            "mobile dev",
            "game developer",
            "android",
            "ios",
            "flutter",
            "react native",
            "developer",
            "programmer",
            "lập trình viên",
            "chuyên viên lập trình",
            "nhân viên lập trình",
            "lập trình",
            "embedded",
            "firmware",
            "kỹ sư phần mềm",
            "java",
            "php",
            "python",
            "node",
            "react",
            "angular",
            "vue",
            ".net",
            "golang",
            "rust",
            "c++",
            "stack developer",
            "software dev",
            "unity",
            "solution architect",
            "software architect",
            "chuyên viên it phần mềm",
            "dev ",
            " dev",
            "engineer",
        ),
    ),
    (
        "IT & Technical Support",
        (
            "helpdesk",
            "help desk",
            "it support",
            "technical support",
            "it helpdesk",
            "application support",
            "nhân viên it",
            "comtor",
            "kỹ thuật viên",
            "support engineer",
            "hỗ trợ kỹ thuật",
            "cộng tác viên it",
            "triển khai phần mềm",
            "triển khai chuyển giao",
        ),
    ),
    (
        "Technical Writing",
        (
            "technical writer",
            "technical writing",
            "technical documentation",
        ),
    ),
]

_DEFAULT = "Other"

_WS = re.compile(r"\s+")


def normalize_job_title(text: object) -> str:
    """Return a coarse role category for grouping similar titles."""
    if text is None or (is_scalar(text) and pd.isna(text)):
        return _DEFAULT
    raw = str(text).strip()
    if not raw or raw.casefold() in ("nan", "none"):
        return _DEFAULT

    s = _WS.sub(" ", raw.lower())

    for category, keywords in _RULES:
        for kw in keywords:
            if kw in s:
                return category
    return _DEFAULT
