from uuid import UUID, uuid4

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from qbank.exams.sampler import Candidate, Row, clusters, matches, sample

CHAPTERS = [uuid4() for _ in range(3)]
STIMULI = [uuid4() for _ in range(4)]
TYPES = ["mcq_single", "true_false", "essay"]
TAGS = ["a", "b", "c"]


@st.composite
def pools(draw: st.DrawFn) -> list[Candidate]:
    ids = draw(st.lists(st.uuids(), min_size=0, max_size=25, unique=True))
    positions: dict[UUID, int] = {}
    out: list[Candidate] = []
    for index, qid in enumerate(ids):
        stimulus = draw(st.sampled_from([None, None, *STIMULI]))
        position = None
        if stimulus is not None:
            position = positions[stimulus] = positions.get(stimulus, 0) + 1
        duplicate = None
        if index and draw(st.integers(0, 4)) == 0:
            duplicate = draw(st.sampled_from(ids[:index]))
        out.append(
            Candidate(
                id=qid,
                chapter_id=draw(st.sampled_from([None, *CHAPTERS])),
                type=draw(st.sampled_from(TYPES)),
                difficulty=draw(st.one_of(st.none(), st.integers(1, 5))),
                tags=draw(st.lists(st.sampled_from(TAGS), max_size=2)),
                stimulus_id=stimulus,
                stimulus_position=position,
                duplicate_of_id=duplicate,
            )
        )
    return out


rows_strategy = st.lists(
    st.builds(
        Row,
        count=st.integers(1, 8),
        chapter_ids=st.lists(st.sampled_from(CHAPTERS), max_size=2),
        types=st.lists(st.sampled_from(TYPES), max_size=2),
        difficulty_min=st.one_of(st.none(), st.integers(1, 5)),
        difficulty_max=st.one_of(st.none(), st.integers(1, 5)),
        tags_any=st.lists(st.sampled_from(TAGS), max_size=2),
    ),
    min_size=1,
    max_size=4,
)


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(pool=pools(), rows=rows_strategy, seed=st.integers(0, 10_000))
def test_sampler_properties(pool: list[Candidate], rows: list[Row], seed: int) -> None:
    results = sample(pool, rows, seed=seed)
    assert results == sample(list(reversed(pool)), rows, seed=seed)  # deterministic, order-free
    by_id = {q.id: q for q in pool}
    cluster = clusters(pool)
    seen: set[UUID] = set()
    seen_clusters: set[UUID] = set()
    for row, result in zip(rows, results, strict=True):
        assert len(result.selected) <= row.count
        assert result.shortfall == row.count - len(result.selected)
        for qid in result.selected:
            assert matches(by_id[qid], row)
            assert qid not in seen
            assert cluster[qid] not in seen_clusters
            seen.add(qid)
            seen_clusters.add(cluster[qid])
        picked = set(result.selected)
        for sid in {by_id[q].stimulus_id for q in picked} - {None}:
            assert {q.id for q in pool if q.stimulus_id == sid} <= picked


def test_exact_fill_with_groups_and_exclusions() -> None:
    four, three, five = 4, 3, 5
    s1, s2 = uuid4(), uuid4()
    group1 = [Candidate(id=uuid4(), stimulus_id=s1, stimulus_position=i) for i in (1, 2)]
    group2 = [Candidate(id=uuid4(), stimulus_id=s2, stimulus_position=i) for i in (1, 2)]
    single = Candidate(id=uuid4())
    pool = [*group1, *group2, single]
    (result,) = sample(pool, [Row(count=four)], seed=1)
    assert len(result.selected) == four
    assert single.id not in result.selected  # two groups hit 4 exactly; a single would not
    (result,) = sample(pool, [Row(count=three)], seed=1)
    assert single.id in result.selected
    assert len(result.selected) == three
    (result,) = sample(pool, [Row(count=1)], seed=1, excluded={single.id})
    assert result.selected == []
    assert result.shortfall == 1
    (result,) = sample(pool, [Row(count=five)], seed=1, fixed={single.id})
    assert result.available == four
    assert len(result.selected) == four


def test_duplicates_are_one_cluster_and_fixed_blocks_cluster() -> None:
    a, b, c = Candidate(id=uuid4()), Candidate(id=uuid4()), Candidate(id=uuid4())
    b = Candidate(id=b.id, duplicate_of_id=a.id)
    c = Candidate(id=c.id, duplicate_of_id=b.id)  # chain a <- b <- c
    (result,) = sample([a, b, c], [Row(count=3)], seed=3)
    assert len(result.selected) == 1
    (result,) = sample([a, b, c], [Row(count=3)], seed=3, fixed={a.id})
    assert result.selected == []
