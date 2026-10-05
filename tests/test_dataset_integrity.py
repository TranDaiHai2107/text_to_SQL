import json
import unittest

from sqlglot import parse_one

from config import EXAMPLES_FILE, SCHEMA_FILE, TEST_FILE
from sql_validator import validate_sql_schema


def canonical_sql(sql: str) -> str:
    return parse_one(sql, read="postgres").sql(
        dialect="postgres",
        normalize=True,
    )


class DatasetIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schemas = json.loads(SCHEMA_FILE.read_text(encoding="utf-8"))
        cls.examples = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
        cls.tests = json.loads(TEST_FILE.read_text(encoding="utf-8"))

    def test_expected_sizes_and_unique_ids(self):
        for records, expected in (
            (self.schemas, 31),
            (self.examples, 101),
            (self.tests, 180),
        ):
            self.assertEqual(len(records), expected)
            ids = [record["id"] for record in records]
            self.assertEqual(len(ids), len(set(ids)))

    def test_all_gold_and_example_sql_pass_validator(self):
        statements = [example["sql"] for example in self.examples]
        statements.extend(item["gold_sql"] for item in self.tests)
        failures = []
        for sql in statements:
            result = validate_sql_schema(sql)
            if not result["valid"]:
                failures.append(result["errors"])
        self.assertFalse(failures, failures[:3])

    def test_evaluation_collection_removes_all_exact_sql_overlap(self):
        gold = {canonical_sql(item["gold_sql"]) for item in self.tests}
        overlapping = [
            example for example in self.examples if canonical_sql(example["sql"]) in gold
        ]
        self.assertEqual(len(overlapping), 28)
        self.assertEqual(len(self.examples) - len(overlapping), 73)


if __name__ == "__main__":
    unittest.main()
