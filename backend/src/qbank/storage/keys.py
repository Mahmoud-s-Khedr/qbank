from uuid import UUID


def prefix(org: UUID, source: UUID) -> str:
    return f"orgs/{org}/sources/{source}/"


def original(org: UUID, source: UUID) -> str:
    return prefix(org, source) + "original.pdf"


def page(org: UUID, source: UUID, number: int, *, hires: bool = False) -> str:
    suffix = "hires.png" if hires else "webp"
    return prefix(org, source) + f"pages/{number:04d}.{suffix}"
