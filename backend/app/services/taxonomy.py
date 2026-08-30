"""
Taxonomy Loader Service — loads failure_taxonomy.yaml once at startup.
Provides O(1) lookup from Razorpay error code → internal FailureCause + metadata.
"""
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import yaml
from app.schemas.enums import FailureCause
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class TaxonomyEntry:
    internal_cause: FailureCause
    retriable: bool | None
    suggested_wait_minutes: int | None
    human_review: bool
    llm_assist: bool
    notes: str


# Sentinel for wildcard fallback
_WILDCARD = "*"


@lru_cache(maxsize=1)
def load_taxonomy(path: str | None = None) -> dict[str, TaxonomyEntry]:
    """
    Builds a flat code → TaxonomyEntry lookup dict from YAML.
    Called once; result cached for the process lifetime.
    """
    yaml_path = Path(path or __file__).parent.parent.parent / "failure_taxonomy.yaml"
    data = yaml.safe_load(yaml_path.read_text())

    lookup: dict[str, TaxonomyEntry] = {}
    wildcard_entry: TaxonomyEntry | None = None

    for mapping in data["mappings"]:
        entry = TaxonomyEntry(
            internal_cause=FailureCause(mapping["internal_cause"]),
            retriable=mapping.get("retriable"),
            suggested_wait_minutes=mapping.get("suggested_wait_minutes"),
            human_review=mapping.get("human_review", False),
            llm_assist=mapping.get("llm_assist", False),
            notes=mapping.get("notes", ""),
        )
        for code in mapping["razorpay_codes"]:
            if code == _WILDCARD:
                wildcard_entry = entry
            else:
                lookup[code] = entry

    # Store wildcard under sentinel key — always present
    if wildcard_entry:
        lookup[_WILDCARD] = wildcard_entry

    logger.info(f"message=Taxonomy loaded | codes={len(lookup)-1} | version={data.get('taxonomy_version')}")
    return lookup


def classify_failure_code(raw_code: str | None) -> TaxonomyEntry:
    """
    Maps a raw Razorpay failure code to a TaxonomyEntry.
    Falls back to wildcard entry for unmapped codes.
    """
    if not raw_code:
        return load_taxonomy()[_WILDCARD]
    taxonomy = load_taxonomy()
    return taxonomy.get(raw_code) or taxonomy[_WILDCARD]
