"""Multi-stage job title classifier.

Pipeline per title:
    Raw Title
        ↓
    Normalize  (strip noise: parentheticals, salary hints, ID codes)
        ↓
    Rule-based  (keyword substring match, ordered by specificity)
        ↓
    TF-IDF cosine similarity  (char n-gram, fallback for unmatched)
        ↓
    Other
"""

from __future__ import annotations

import logging
import re

import pandas as pd
from pandas.api.types import is_scalar

logger = logging.getLogger(__name__)

# ── Stage 1: Normalize ────────────────────────────────────────────────────────

# Noise patterns stripped before classification (order matters)
_NOISE: list[re.Pattern[str]] = [
    re.compile(r"\s*\([^)]{0,120}\)", re.U),                          # (parenthetical content)
    re.compile(r"\s*\[[^\]]{0,80}\]", re.U),                          # [bracket content]
    re.compile(r"\s*[-–—|]\s*(salary|lương|thu nhập)[^,;]*", re.I),   # - Salary Up To …
    re.compile(r"\s*[-–—|]\s*(?:upto|up\s*to)\s+\S+", re.I),          # - Upto 25M
    re.compile(r"\s*_j\d+\b", re.I),                                   # _J1234567 job codes
    re.compile(r"\s*[-–—|]\s*t\d{4,}\b", re.I),                        # | T9160 codes
]
_WS = re.compile(r"\s+")


def _normalize(raw: str) -> str:
    """Strip noise tokens and return a lowercase, space-normalised string."""
    s = raw
    for pat in _NOISE:
        s = pat.sub(" ", s)
    return _WS.sub(" ", s).strip().lower()


# ── Stage 2: Rule-based ───────────────────────────────────────────────────────

# Longer / more specific phrases first within each category.
# First matching category wins (list order = priority).
_RULES: list[tuple[str, tuple[str, ...]]] = [
    (
        "Project & Product Management",
        (
            "project manager", "product owner", "product manager",
            "scrum master", "quản lý dự án", "it project manager",
            "product lead", "agile coach", "it manager",
            "technical service manager", "delivery manager",
            "trưởng phòng it", "technical manager", "trưởng bộ phận it",
        ),
    ),
    (
        "DevOps & Cloud",
        (
            "devops", "sre", "site reliability", "kubernetes", "k8s",
            "infrastructure engineer", "cloud engineer", "ci/cd",
            "system engineer", "systems engineer",
            "kỹ thuật hệ thống", "kỹ sư hệ thống",
            "it infra", " infra ", "infra lead",
            "system admin", "vận hành cloud", "cloud operations",
        ),
    ),
    (
        "Data & Analytics",
        (
            "data engineer", "data scientist", "data analyst",
            "business intelligence", "bi developer", "data science",
            "machine learning", "ml engineer", "ai engineer",
            "deep learning", "big data", "data admin",
            "data manager", " chuyên viên bi", " cao cấp bi",
            " BI ", " BI)",
        ),
    ),
    (
        "Business Analysis",
        (
            "business analyst", "business analysis", "business analyses",
            "chuyên viên phân tích nghiệp vụ", "functional analyst",
            "system analyst", "brse", "kỹ sư cầu nối",
            "fresher ba", " ba ",
        ),
    ),
    (
        "QA & Testing",
        (
            "quality assurance", "test automation", "automation test",
            "manual test", "kiểm thử", "tester", "testing engineer",
            "qa engineer", "qa ", " qa", "qc engineer", "quality engineer",
            "software test", "kiểm định", "pqa",
            "kiểm soát quy trình", "quản lý chất lượng",
            "quality management", "test lead", "test leader",
            "qa/qc leader", "qa/qc",
            "thực tập sinh qc",
        ),
    ),
    (
        "Security",
        (
            "security engineer", "security architect", "security solution",
            "cybersecurity", "cyber security", "an ninh mạng",
            "bảo mật thông tin", "pentest", "penetration",
            "chuyên viên soc", " soc ",
        ),
    ),
    (
        "Design & UX",
        (
            "ui/ux", "ux designer", "ui designer", "graphic design",
            "designer", "thiết kế", "ux/", "ui/",
            "chuyên gia ui ux", "video editor", "2d game animation",
        ),
    ),
    (
        "Marketing & Content",
        (
            "marketing", "digital marketing", "seo",
            "content marketing", "content writer", "content seeding",
            "growth hacker", "senior pr",
        ),
    ),
    (
        "Sales & Business Development",
        (
            "business development", "account manager", "sales executive",
            "kinh doanh", "telesales",
        ),
    ),
    (
        "Network & Infrastructure",
        (
            "network engineer", "network administrator", "network admin",
            "quản trị mạng", "kỹ thuật mạng", "system network",
            "database administrator", "database admin", "dba",
            "sysadmin", "system administrator", "giảng viên ccna",
            "kỹ sư robotics",
        ),
    ),
    (
        "Software Development",
        (
            "software engineer", "tech lead", "technical lead",
            "team lead", "lead developer", "lead back-end",
            "fullstack", "full-stack", "full stack",
            "backend", "front-end", "frontend", "front end",
            "web developer", "mobile developer", "mobile dev",
            "game developer", "android", "ios", "flutter",
            "react native", "developer", "programmer",
            "lập trình viên", "chuyên viên lập trình",
            "nhân viên lập trình", "lập trình", "embedded",
            "firmware", "kỹ sư phần mềm", "java", "php",
            "python", "node", "react", "angular", "vue",
            ".net", "golang", "rust", "c++", "stack developer",
            "software dev", "unity", "solution architect",
            "software architect", "chuyên viên it phần mềm",
            "ruby on rails", "blockchain", "smartcontract",
            "cocos creator", "nhân viên r&d", "ai intern",
            "mobile intern", "dev ", " dev", "engineer",
        ),
    ),
    (
        "IT & Technical Support",
        (
            "helpdesk", "help desk", "it support", "technical support",
            "it helpdesk", "application support", "nhân viên it",
            "it nội bộ", "chuyên viên it", "chuyên viên cntt",
            "comtor", "kỹ thuật viên", "support engineer",
            "hỗ trợ kỹ thuật", "cộng tác viên it",
            "triển khai phần mềm", "triển khai chuyển giao",
            "service desk", "it communicator",
        ),
    ),
    (
        "Technical Writing",
        (
            "technical writer", "technical writing", "technical documentation",
        ),
    ),
]

_DEFAULT = "Other"


# ── Stage 3: TF-IDF embedding similarity ─────────────────────────────────────

# Seed phrases per category used to build the TF-IDF index.
_SEEDS: dict[str, list[str]] = {
    "Software Development": [
        "backend developer", "frontend developer", "fullstack developer",
        "software engineer", "web developer", "mobile developer",
        "lập trình viên", "kỹ sư phần mềm", "game developer",
        "ios developer", "android developer", "flutter developer",
        "nodejs developer", "react developer", "php developer",
        "java developer", "python developer", "golang developer",
        ".net developer", "c++ engineer", "embedded engineer",
        "solution architect", "software architect", "tech lead",
        "ruby on rails developer", "blockchain developer",
        "smart contract developer",
    ],
    "DevOps & Cloud": [
        "devops engineer", "cloud engineer", "site reliability engineer",
        "infrastructure engineer", "system administrator", "sre engineer",
        "kỹ sư hệ thống", "vận hành hệ thống", "cloud operations",
        "kubernetes engineer", "platform engineer",
    ],
    "Data & Analytics": [
        "data engineer", "data analyst", "data scientist",
        "business intelligence analyst", "machine learning engineer",
        "ai engineer", "big data engineer", "kỹ sư dữ liệu",
        "phân tích dữ liệu", "data manager",
    ],
    "Business Analysis": [
        "business analyst", "system analyst", "functional analyst",
        "phân tích nghiệp vụ", "chuyên viên phân tích", "brse",
        "kỹ sư cầu nối",
    ],
    "QA & Testing": [
        "quality assurance engineer", "software tester", "qa engineer",
        "test automation engineer", "manual tester", "kiểm thử phần mềm",
        "chuyên viên kiểm thử", "test lead", "qa lead", "qc leader",
    ],
    "Project & Product Management": [
        "project manager", "product manager", "product owner",
        "scrum master", "delivery manager", "program manager",
        "quản lý dự án", "quản lý sản phẩm", "trưởng phòng",
        "technical manager",
    ],
    "Network & Infrastructure": [
        "network engineer", "network administrator", "database administrator",
        "system network engineer", "quản trị mạng", "kỹ thuật mạng",
        "dba engineer", "kỹ sư robotics", "robotics engineer",
    ],
    "IT & Technical Support": [
        "it support engineer", "helpdesk technician", "technical support",
        "application support", "it technician", "hỗ trợ kỹ thuật",
        "nhân viên it", "triển khai phần mềm", "service desk engineer",
        "it nội bộ", "chuyên viên cntt",
    ],
    "Security": [
        "security engineer", "cybersecurity analyst", "penetration tester",
        "information security", "an ninh mạng", "soc analyst",
        "security operations",
    ],
    "Design & UX": [
        "ui ux designer", "graphic designer", "product designer",
        "ux researcher", "thiết kế đồ họa", "web designer",
        "video editor", "animation artist",
    ],
    "Marketing & Content": [
        "digital marketing specialist", "seo specialist", "content writer",
        "marketing manager", "content creator", "brand executive",
    ],
    "Sales & Business Development": [
        "business development manager", "sales executive", "account manager",
        "kinh doanh", "phát triển thị trường",
    ],
}

_SIMILARITY_THRESHOLD = 0.30


class _TFIDFClassifier:
    """TF-IDF char-n-gram cosine similarity fallback.

    Gracefully degrades to a no-op if scikit-learn is unavailable.
    Built once at import time; zero overhead per-call after that.
    """

    def __init__(self) -> None:
        self._ready = False
        self._vectorizer = None
        self._matrix = None
        self._labels: list[str] = []
        self._build()

    def _build(self) -> None:
        try:
            from sklearn.feature_extraction.text import TfidfVectorizer

            corpus: list[str] = []
            for category, phrases in _SEEDS.items():
                for phrase in phrases:
                    corpus.append(phrase)
                    self._labels.append(category)

            self._vectorizer = TfidfVectorizer(
                analyzer="char_wb",
                ngram_range=(2, 4),
                sublinear_tf=True,
            )
            self._matrix = self._vectorizer.fit_transform(corpus)
            self._ready = True
            logger.debug("TF-IDF classifier built: %d seed phrases", len(corpus))
        except ImportError:
            logger.warning(
                "scikit-learn not installed — embedding fallback disabled. "
                "Run: pip install scikit-learn"
            )

    def predict(self, text: str) -> str | None:
        if not self._ready:
            return None

        from sklearn.metrics.pairwise import cosine_similarity
        import numpy as np

        vec = self._vectorizer.transform([text])
        sims = cosine_similarity(vec, self._matrix)[0]
        best_idx = int(np.argmax(sims))
        best_score = float(sims[best_idx])

        if best_score >= _SIMILARITY_THRESHOLD:
            logger.debug(
                "Embedding: %r → %r (score=%.3f)",
                text, self._labels[best_idx], best_score,
            )
            return self._labels[best_idx]
        return None


# Built once at import — negligible overhead (~5ms)
_classifier = _TFIDFClassifier()


# ── Public API ────────────────────────────────────────────────────────────────

def classify_job_title(text: object) -> tuple[str, str]:
    """Return ``(category, method)`` — method is one of ``rule``, ``embedding``, ``other``.

    Useful for auditing classification quality.
    """
    if text is None or (is_scalar(text) and pd.isna(text)):
        return (_DEFAULT, "other")
    raw = str(text).strip()
    if not raw or raw.casefold() in ("nan", "none"):
        return (_DEFAULT, "other")

    normalized = _normalize(raw)

    # Stage 2: rule-based
    for category, keywords in _RULES:
        for kw in keywords:
            if kw in normalized:
                return (category, "rule")

    # Stage 3: embedding similarity
    result = _classifier.predict(normalized)
    if result:
        return (result, "embedding")

    return (_DEFAULT, "other")


def normalize_job_title(text: object) -> str:
    """Return role category string (for use in DataFrame.apply)."""
    category, _ = classify_job_title(text)
    return category
