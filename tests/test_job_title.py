"""Unit tests for job title normalization."""

import pytest
from etl.transform.job_title import normalize_job_title


@pytest.mark.parametrize("title, expected_category", [
    # Software Development
    ("Senior Backend Developer",           "Software Development"),
    ("Fullstack Engineer",                 "Software Development"),
    ("Lập Trình Viên PHP",                 "Software Development"),
    ("Nhân Viên Lập Trình Web",            "Software Development"),
    ("Junior Java Developer",              "Software Development"),
    (".Net Developer",                     "Software Development"),

    # DevOps & Cloud
    ("Devops/SRE",                         "DevOps & Cloud"),
    ("Chuyên Viên Vận Hành Cloud",         "DevOps & Cloud"),
    ("IT Infra Lead",                      "DevOps & Cloud"),

    # Data & Analytics
    ("Data Analyst",                       "Data & Analytics"),
    ("Data Engineer",                      "Data & Analytics"),
    ("AI Engineer",                        "Data & Analytics"),
    ("Chuyên Gia Big Data",                "Data & Analytics"),

    # Business Analysis
    ("Business Analyst",                   "Business Analysis"),
    ("Chuyên Viên Phân Tích Nghiệp Vụ",   "Business Analysis"),

    # QA & Testing
    ("QA Tester",                          "QA & Testing"),
    ("Software Tester",                    "QA & Testing"),
    ("Chuyên Viên Kiểm Thử Phần Mềm",     "QA & Testing"),

    # Project & Product Management
    ("IT Project Manager",                 "Project & Product Management"),
    ("Product Owner (Upto 25M)",           "Project & Product Management"),
    ("Delivery Manager",                   "Project & Product Management"),

    # Network & Infrastructure
    ("Network Engineer",                   "Network & Infrastructure"),
    ("Database Administrator (DBA)",       "Network & Infrastructure"),
    ("Nhân Viên Kỹ Thuật Mạng",           "Network & Infrastructure"),

    # IT & Technical Support
    ("IT Application Support",             "IT & Technical Support"),
    ("Nhân Viên IT Helpdesk",              "IT & Technical Support"),

    # Security
    ("Security Solution Architect",        "Security"),

    # Design & UX
    ("UI/UX Designer",                     "Design & UX"),

    # Other / no match
    ("Secretary",                          "Other"),
    (None,                                 "Other"),
    ("",                                   "Other"),
    ("nan",                                "Other"),
])
def test_normalize_job_title(title, expected_category):
    assert normalize_job_title(title) == expected_category
