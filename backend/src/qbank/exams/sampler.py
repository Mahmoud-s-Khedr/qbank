"""Blueprint sampler: pick approved questions for each blueprint row, deterministically."""

import random
from collections import defaultdict
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass, field
from uuid import UUID


@dataclass(frozen=True)
class Candidate:
    id: UUID
    chapter_id: UUID | None = None
    lesson_id: UUID | None = None
    type: str = "mcq_single"
    difficulty: int | None = None
    tags: Sequence[str] = ()
    stimulus_id: UUID | None = None
    stimulus_position: int | None = None
    duplicate_of_id: UUID | None = None


@dataclass(frozen=True)
class Row:
    count: int
    chapter_ids: Collection[UUID] = ()
    lesson_ids: Collection[UUID] = ()
    types: Collection[str] = ()
    difficulty_min: int | None = None
    difficulty_max: int | None = None
    tags_any: Collection[str] = ()


@dataclass
class RowResult:
    requested: int
    selected: list[UUID] = field(default_factory=list)
    available: int = 0

    @property
    def shortfall(self) -> int:
        return self.requested - len(self.selected)


def _difficulty_ok(question: Candidate, row: Row) -> bool:
    if row.difficulty_min is None and row.difficulty_max is None:
        return True
    if question.difficulty is None:
        return False
    return (row.difficulty_min is None or question.difficulty >= row.difficulty_min) and (
        row.difficulty_max is None or question.difficulty <= row.difficulty_max
    )


def matches(question: Candidate, row: Row) -> bool:
    return (
        (not row.chapter_ids or question.chapter_id in row.chapter_ids)
        and (not row.lesson_ids or question.lesson_id in row.lesson_ids)
        and (not row.types or question.type in row.types)
        and _difficulty_ok(question, row)
        and (not row.tags_any or bool(set(row.tags_any) & set(question.tags)))
    )


def clusters(pool: Iterable[Candidate]) -> dict[UUID, UUID]:
    """Map every question id to its duplicate-cluster representative (links are undirected)."""
    parent: dict[UUID, UUID] = {}

    def find(x: UUID) -> UUID:
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for q in pool:
        find(q.id)
        if q.duplicate_of_id is not None:
            a, b = find(q.id), find(q.duplicate_of_id)
            if a != b:
                parent[max(a, b)] = min(a, b)  # smallest id wins: independent of input order
    return {x: find(x) for x in list(parent)}


def _subset(sizes: Sequence[int], target: int) -> list[int] | None:
    """Indices of a subset of `sizes` summing to `target` (earliest items preferred)."""
    reach: dict[int, list[int]] = {0: []}
    for index, size in enumerate(sizes):
        for total, picked in list(reach.items()):
            if total + size <= target and total + size not in reach:
                reach[total + size] = [*picked, index]
    return reach.get(target)


def _choose(
    singles: list[list[Candidate]], groups: list[list[Candidate]], count: int
) -> list[list[Candidate]]:
    """Prefer singles; fill the rest with groups that fit. Exact when possible, never over."""
    sizes = [len(g) for g in groups]
    for total in range(count, 0, -1):
        for n_singles in range(min(total, len(singles)), -1, -1):
            picked = _subset(sizes, total - n_singles)
            if picked is not None:
                return [*singles[:n_singles], *(groups[i] for i in picked)]
    return []


def sample(  # noqa: PLR0913 -- sampler options are independently useful
    pool: Sequence[Candidate],
    rows: Sequence[Row],
    *,
    seed: int,
    excluded: Collection[UUID] = (),
    fixed: Collection[UUID] = (),
    oversample: int = 1,
) -> list[RowResult]:
    """Fill `rows` in order from `pool` (approved questions of one subject).

    `excluded` ids are never picked; `fixed` ids are already in the exam, so they and their
    duplicates are off limits too. Deterministic for equal inputs and seed.
    """
    rng = random.Random(seed)  # noqa: S311 -- shuffling, not cryptography
    ordered = sorted(pool, key=lambda q: q.id)
    cluster = clusters(ordered)
    members: dict[UUID, list[Candidate]] = defaultdict(list)
    for q in ordered:
        if q.stimulus_id is not None:
            members[q.stimulus_id].append(q)
    for group in members.values():
        group.sort(key=lambda q: (q.stimulus_position or 0, q.id))
    blocked = set(excluded) | set(fixed)
    used_clusters = {cluster[q] for q in fixed if q in cluster}
    results: list[RowResult] = []
    for row in rows:
        result = RowResult(requested=row.count)
        results.append(result)
        units: list[list[Candidate]] = []
        seen_groups: set[UUID] = set()
        for q in ordered:
            if q.stimulus_id is None:
                units.append([q])
            elif q.stimulus_id not in seen_groups:
                seen_groups.add(q.stimulus_id)
                units.append(members[q.stimulus_id])
        eligible = [
            u
            for u in units
            if all(matches(q, row) and q.id not in blocked for q in u)
            and len({cluster[q.id] for q in u}) == len(u)
            and not {cluster[q.id] for q in u} & used_clusters
        ]
        rng.shuffle(eligible)
        free: list[list[Candidate]] = []
        taken: set[UUID] = set()
        for unit in eligible:  # one representative per duplicate cluster
            keys = {cluster[q.id] for q in unit}
            if keys & taken:
                continue
            taken |= keys
            free.append(unit)
        result.available = sum(len(u) for u in free)
        singles = [u for u in free if len(u) == 1]
        groups = [u for u in free if len(u) > 1]
        for unit in _choose(singles, groups, row.count * oversample):
            result.selected.extend(q.id for q in unit)
            for q in unit:
                blocked.add(q.id)
                used_clusters.add(cluster[q.id])
    return results
