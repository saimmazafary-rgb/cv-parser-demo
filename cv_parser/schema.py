"""Output schema for parsed CVs.

This mirrors the target JSON structure exactly, so the utility's output can be
saved straight into the database without any remapping. Every record is one CV;
`parsedData` holds the normalized fields.
"""
from __future__ import annotations

from typing import Any


# Field lists kept as constants so extraction and validation share one source
# of truth (add a field here and it flows through the whole pipeline).
PERSONAL_DETAIL_FIELDS = [
    "name", "position", "email", "phone", "city", "country", "linkedin",
    "website", "religion", "ethnicity", "smokingStatus", "militaryService",
    "isArab", "passportNo", "passportExpiry", "civilId", "visaNumber",
    "visaExpiry", "drivingLicense",
]


def empty_personal_details() -> dict[str, Any]:
    return {field: None for field in PERSONAL_DETAIL_FIELDS}


def empty_parsed_data() -> dict[str, Any]:
    """A parsedData object with every key present and empty.

    Keeping the shape stable (never dropping keys) is what lets downstream code
    and QA rely on the schema instead of guarding every access.
    """
    return {
        "personalDetails": empty_personal_details(),
        "summary": "",
        "workExperience": [],   # {company, role, startDate, endDate, description}
        "education": [],        # {institution, degree, major, cgpa, endDate}
        "skills": [],           # {category, skills, yearsExperience, proficiency}
        "languages": [],        # {languageName, speakingLevel, readingLevel, writingLevel}
        "projects": [],         # {name, description, technologies}
        "certifications": [],   # {certificateName, issuer, issueDate, expiryDate}
        "preferences": {
            "preferredJobTitle": None,
            "expectedSalary": None,
            "salaryCurrency": None,
            "availabilityDate": None,
        },
    }


def empty_record() -> dict[str, Any]:
    return {
        "id": None,
        "fileName": None,
        "fileSize": None,
        "fileType": None,
        "text": "",
        "status": "pending",
        "parsedData": empty_parsed_data(),
        "selected": False,
        "onboarded": False,
    }
