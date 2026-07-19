"""Prepare the canonical/approved BigQuery recipe-detail store.

This is an operator step, not a web-request side effect. It copies RecipeNLG's
ingredient and direction text into ``sous.recipe_details`` and marks those rows
as corpus-backed. Search fallbacks stay unreviewed in the app until a human
promotes them into this table.

Usage:
    python scripts/prepare_recipe_details.py --dry-run
    python scripts/prepare_recipe_details.py
    python scripts/prepare_recipe_details.py --create-only
    python scripts/prepare_recipe_details.py \
        --source-table sous-500915.sous.recipes_full
"""
import argparse
import os
import re


PROJECT = os.environ.get("SOUS_PROJECT_ID", "sous-500915")
DATASET = os.environ.get("SOUS_DATASET", "sous")
DEFAULT_SOURCE = f"{PROJECT}.{DATASET}.recipes"
TARGET = os.environ.get(
    "SOUS_RECIPE_DETAILS_TABLE", f"{PROJECT}.{DATASET}.recipe_details")


CREATE_SQL = f"""
CREATE TABLE IF NOT EXISTS `{TARGET}` (
  recipe_key STRING NOT NULL,
  title STRING,
  raw_title STRING,
  ingredients STRING,
  directions STRING,
  source_type STRING,
  source_name STRING,
  source_url STRING,
  source_urls STRING,
  quality_status STRING,
  updated_at TIMESTAMP
)
CLUSTER BY recipe_key
""".strip()


def table_id(value: str) -> str:
    """Accept only a fully-qualified BigQuery table identifier."""
    value = value.strip().strip("`")
    part = r"[A-Za-z0-9][A-Za-z0-9_-]*"
    if not re.fullmatch(rf"{part}\.{part}\.{part}", value):
        raise argparse.ArgumentTypeError(
            "expected a fully-qualified table: project.dataset.table")
    return value


def merge_sql(source_table: str) -> str:
    return f"""
MERGE `{TARGET}` AS target
USING (
  WITH complete_rows AS (
    SELECT
      REGEXP_REPLACE(LOWER(TRIM(title)), r'[^a-z0-9]+', ' ') AS recipe_key,
      title,
      ingredients,
      directions
    FROM `{source_table}`
    WHERE title IS NOT NULL
      AND NULLIF(TRIM(ingredients), '') IS NOT NULL
      AND NULLIF(TRIM(directions), '') IS NOT NULL
  ),
  ranked_rows AS (
    SELECT *,
      ROW_NUMBER() OVER (
        PARTITION BY recipe_key
        ORDER BY LENGTH(directions) DESC,
                 LENGTH(ingredients) DESC,
                 title
      ) AS detail_rank
    FROM complete_rows
  )
  SELECT
    recipe_key, title, title AS raw_title, ingredients, directions
  FROM ranked_rows
  WHERE detail_rank = 1
) AS source
ON target.recipe_key = source.recipe_key AND target.source_type = 'corpus'
WHEN MATCHED THEN UPDATE SET
  title = source.title,
  raw_title = source.raw_title,
  ingredients = source.ingredients,
  directions = source.directions,
  source_name = 'RecipeNLG corpus via BigQuery',
  quality_status = 'corpus',
  updated_at = CURRENT_TIMESTAMP()
WHEN NOT MATCHED THEN INSERT (
  recipe_key, title, raw_title, ingredients, directions, source_type,
  source_name, source_url, source_urls, quality_status, updated_at
) VALUES (
  source.recipe_key, source.title, source.raw_title, source.ingredients,
  source.directions, 'corpus', 'RecipeNLG corpus via BigQuery', NULL, '[]',
  'corpus', CURRENT_TIMESTAMP()
)
""".strip()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="print the DDL/DML without contacting BigQuery")
    parser.add_argument(
        "--create-only", action="store_true",
        help="ensure the approved table schema exists without importing rows",
    )
    parser.add_argument(
        "--source-table", type=table_id, default=DEFAULT_SOURCE,
        help=("complete RecipeNLG source table; must include title, ingredients "
              "and directions (default: %(default)s)"),
    )
    args = parser.parse_args()
    source_table = args.source_table
    sql = merge_sql(source_table)
    if args.dry_run:
        print(CREATE_SQL)
        if not args.create_only:
            print("\n" + sql)
        return

    from google.cloud import bigquery
    from google.api_core.exceptions import NotFound
    client = bigquery.Client(project=PROJECT)
    if args.create_only:
        client.query(CREATE_SQL).result()
        print(f"Ensured {TARGET} exists; no corpus rows were imported.")
        return

    try:
        source = client.get_table(source_table)
    except NotFound:
        print(
            f"Skipped corpus import: {source_table} does not exist. "
            f"{TARGET} remains ready for reviewed rows; Gemini + Search "
            "stays a labelled fallback."
        )
        return
    columns = {field.name.lower() for field in source.schema}
    missing = {"title", "ingredients", "directions"} - columns
    if missing:
        raise SystemExit(
            f"No changes were made. {source_table} is missing: "
            + ", ".join(sorted(missing)) + ".\n"
            "Reload the original full RecipeNLG CSV into a separate BigQuery "
            "table (for example, sous.recipes_full), then rerun:\n"
            "  python scripts/prepare_recipe_details.py --source-table "
            f"{PROJECT}.{DATASET}.recipes_full\n"
            "Gemini Search is intentionally a labelled fallback, not a repair "
            "mechanism for canonical source data."
        )
    client.query(CREATE_SQL).result()
    job = client.query(sql)
    job.result()
    print(
        f"Prepared {TARGET} from {source_table}; "
        f"affected rows: {job.num_dml_affected_rows}"
    )


if __name__ == "__main__":
    main()
