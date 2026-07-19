import argparse
import sys

import pytest

from scripts import prepare_recipe_details as prep


def test_table_id_requires_fully_qualified_safe_identifier():
    assert prep.table_id("`sous-500915.sous.recipes_full`") == (
        "sous-500915.sous.recipes_full"
    )
    with pytest.raises(argparse.ArgumentTypeError):
        prep.table_id("sous.recipes")
    with pytest.raises(argparse.ArgumentTypeError):
        prep.table_id("sous-500915.sous.recipes`; DROP TABLE x")


def test_merge_uses_one_complete_coherent_recipe_row():
    sql = prep.merge_sql("sous-500915.sous.recipes_full")
    assert "FROM `sous-500915.sous.recipes_full`" in sql
    assert "NULLIF(TRIM(directions), '') IS NOT NULL" in sql
    assert "ROW_NUMBER() OVER" in sql
    assert "WHERE detail_rank = 1" in sql
    assert "ANY_VALUE" not in sql


def test_missing_optional_source_is_a_clean_skip(monkeypatch, capsys):
    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery

    class MissingSourceClient:
        def get_table(self, _table):
            raise NotFound("missing")

    monkeypatch.setattr(
        bigquery, "Client", lambda project: MissingSourceClient())
    monkeypatch.setattr(
        sys, "argv",
        ["prepare_recipe_details.py", "--source-table",
         "sous-500915.sous.recipes_full"],
    )

    assert prep.main() is None
    output = capsys.readouterr().out
    assert "Skipped corpus import" in output
    assert "does not exist" in output
