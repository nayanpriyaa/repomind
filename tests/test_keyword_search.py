"""FTS5 lexical search: ranking, scoping and query sanitisation."""

from __future__ import annotations

from conftest import make_chunk

from repomind.keyword_search import KeywordIndex, build_match_expression

REPO = "/repositories/sample"


def seed(index: KeywordIndex) -> None:
    index.index_chunks(
        [
            make_chunk(
                "auth",
                symbol="authenticateUser",
                file_path="app/auth.py",
                content="def authenticateUser(token):\n    return verify_signature(token)\n",
            ),
            make_chunk(
                "db",
                symbol="connect",
                file_path="app/database.py",
                content="def connect(dsn):\n    return psycopg.connect(dsn)\n",
            ),
            make_chunk(
                "util",
                symbol="slugify",
                file_path="app/utils.py",
                content="def slugify(value):\n    return value.lower().replace(' ', '-')\n",
            ),
        ]
    )


def test_search_finds_a_symbol_by_exact_name(keyword_index: KeywordIndex) -> None:
    seed(keyword_index)
    hits = keyword_index.search("authenticateUser", top_k=5)
    assert hits[0].chunk_id == "auth"


def test_search_matches_camel_case_components(keyword_index: KeywordIndex) -> None:
    seed(keyword_index)
    hits = keyword_index.search("authenticate", top_k=5)
    assert any(hit.chunk_id == "auth" for hit in hits)


def test_symbol_matches_outrank_body_matches(keyword_index: KeywordIndex) -> None:
    keyword_index.index_chunks(
        [
            make_chunk("named", symbol="cache", file_path="a.py", content="def cache():\n    return None\n"),
            make_chunk("mentioned", symbol="unrelated", file_path="b.py", content="# a passing note about cache behaviour here\nvalue = 1\n"),
        ]
    )
    hits = keyword_index.search("cache", top_k=5)
    assert hits[0].chunk_id == "named"


def test_search_matches_file_paths(keyword_index: KeywordIndex) -> None:
    seed(keyword_index)
    hits = keyword_index.search("database", top_k=5)
    assert any(hit.file_path == "app/database.py" for hit in hits)


def test_scores_are_higher_is_better(keyword_index: KeywordIndex) -> None:
    seed(keyword_index)
    hits = keyword_index.search("authenticateUser token", top_k=5)
    assert hits == sorted(hits, key=lambda hit: hit.score, reverse=True)


def test_search_is_scoped_to_one_repository(keyword_index: KeywordIndex) -> None:
    keyword_index.index_chunks([make_chunk("one", symbol="shared", repository_path="/repositories/one")])
    keyword_index.index_chunks([make_chunk("two", symbol="shared", repository_path="/repositories/two")])
    hits = keyword_index.search("shared", top_k=5, repository_path="/repositories/one")
    assert [hit.chunk_id for hit in hits] == ["one"]


def test_hits_carry_display_symbols_not_expanded_ones(keyword_index: KeywordIndex) -> None:
    seed(keyword_index)
    hit = keyword_index.search("authenticateUser", top_k=1)[0]
    assert hit.symbol == "authenticateUser"


def test_delete_file_removes_only_that_file(keyword_index: KeywordIndex) -> None:
    seed(keyword_index)
    keyword_index.delete_file(REPO, "app/auth.py")
    assert keyword_index.search("authenticateUser", top_k=5) == []
    assert keyword_index.search("slugify", top_k=5) != []


def test_delete_repository_empties_the_index(keyword_index: KeywordIndex) -> None:
    seed(keyword_index)
    keyword_index.delete_repository(REPO)
    assert keyword_index.count(REPO) == 0


def test_unmatched_query_returns_nothing(keyword_index: KeywordIndex) -> None:
    seed(keyword_index)
    assert keyword_index.search("zzzznonexistent", top_k=5) == []


def test_fts_operators_in_user_input_cannot_break_the_query(keyword_index: KeywordIndex) -> None:
    seed(keyword_index)
    for hostile in ['" OR chunks_fts MATCH "', "NEAR(a b", "connect*", '"""', "^"]:
        keyword_index.search(hostile, top_k=5)  # must not raise


def test_build_match_expression_quotes_and_or_joins_terms() -> None:
    expression = build_match_expression("where is auth handled")
    assert '"where"' in expression and " OR " in expression
    assert expression.count('"') % 2 == 0


def test_build_match_expression_splits_identifiers() -> None:
    expression = build_match_expression("getUserToken")
    assert '"getusertoken"' in expression
    assert '"user"' in expression


def test_build_match_expression_is_empty_for_punctuation_only() -> None:
    assert build_match_expression("?? !!") == ""
