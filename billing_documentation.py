import re
from pathlib import Path
from typing import TypedDict


GUIDE_PATH = Path(__file__).with_name("Mobile_Provider_Billing_Guide.md")
DOCUMENT_ID = re.compile(r"^\*\*Document ID:\*\*[ \t]*(\S+)", re.MULTILINE)
SECTION_HEADING = re.compile(
    r"^#{2,3}[ \t]+(\d+(?:\.\d+)*)\.?[ \t]+(.+)$", re.MULTILINE
)
WORD = re.compile(r"[^\W_]+")
COMMON_WORDS = set("a an are can do does for how i is me much my of only the to what".split())
EQUIVALENT_WORDS = {
    "additional": "extra",
    "costs": "cost",
    "disputes": "dispute",
    "part": "partial",
    "payment": "pay",
    "payments": "pay",
}


class BillingSection(TypedDict):
    document_id: str
    section: str
    heading: str
    text: str


def load_billing_sections(path: Path = GUIDE_PATH) -> list[BillingSection]:
    """Read the guide and return each numbered section with its own text."""
    guide = path.read_text(encoding="utf-8")
    document_id = DOCUMENT_ID.search(guide)
    if document_id is None:
        raise ValueError(f"Missing document ID in {path.name}")

    headings = list(SECTION_HEADING.finditer(guide))
    sections: list[BillingSection] = []
    for index, heading in enumerate(headings):
        next_heading = headings[index + 1] if index + 1 < len(headings) else None
        end = next_heading.start() if next_heading is not None else len(guide)
        section_text = guide[heading.end():end].strip()
        if section_text:
            sections.append({
                "document_id": document_id.group(1),
                "section": heading.group(1),
                "heading": heading.group(2).strip(),
                "text": section_text,
            })
    return sections


def search_terms(text: str) -> set[str]:
    return {
        EQUIVALENT_WORDS.get(word, word)
        for word in WORD.findall(text.casefold())
        if word not in COMMON_WORDS
    }


class BillingSearchIndex:
    def __init__(self, sections: list[BillingSection]):
        self._entries = [
            (section, search_terms(section["heading"]), search_terms(section["text"]))
            for section in sections
        ]

    def search(self, query: str, limit: int = 3) -> list[BillingSection]:
        terms = search_terms(query)
        matches = []
        for section, heading_terms, text_terms in self._entries:
            # A term in the heading gives a stronger signal about the section's topic.
            score = 2 * len(terms & heading_terms) + len(terms & text_terms)
            if score > 0:
                matches.append((score, section))

        matches.sort(key=lambda match: match[0], reverse=True)
        return [section for _, section in matches[:max(0, limit)]]
