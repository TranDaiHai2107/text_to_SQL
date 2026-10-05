import unittest

from sql_validator import validate_sql_schema


class SqlValidatorTests(unittest.TestCase):
    def assert_valid(self, sql: str) -> None:
        result = validate_sql_schema(sql)
        self.assertTrue(result["valid"], result["errors"])

    def assert_invalid(self, sql: str) -> None:
        result = validate_sql_schema(sql)
        self.assertFalse(result["valid"], result)

    def test_accepts_select_alias_cte_and_timestamp_expression(self):
        self.assert_valid("SELECT p.subject_id FROM patients AS p")
        self.assert_valid(
            "WITH older AS (SELECT subject_id FROM patients WHERE anchor_age > 65) "
            "SELECT COUNT(*) FROM older"
        )
        self.assert_valid(
            "SELECT EXTRACT(HOUR FROM admittime) AS hour FROM admissions"
        )

    def test_does_not_treat_string_content_as_sql(self):
        self.assert_valid("SELECT subject_id FROM admissions WHERE admission_type = 'drop'")

    def test_rejects_unknown_tables_and_columns(self):
        self.assert_invalid("SELECT subject_id FROM imaginary_table")
        self.assert_invalid("SELECT p.nonexistent FROM patients AS p")
        self.assert_invalid("SELECT nonexistent FROM patients")

    def test_rejects_multiple_or_mutating_statements(self):
        self.assert_invalid("SELECT subject_id FROM patients; SELECT hadm_id FROM admissions")
        self.assert_invalid("DELETE FROM patients")
        self.assert_invalid("SELECT subject_id INTO temp_ids FROM patients")
        self.assert_invalid("SELECT subject_id FROM patients FOR UPDATE")

    def test_rejects_dangerous_functions_and_other_schemas(self):
        self.assert_invalid("SELECT pg_read_file('/etc/passwd') FROM patients LIMIT 1")
        self.assert_invalid("SELECT pg_sleep(1) FROM patients LIMIT 1")
        self.assert_invalid("SELECT nextval('unsafe_sequence') FROM patients LIMIT 1")
        self.assert_invalid("SELECT subject_id FROM private.patients")

    def test_requires_complete_icd_dictionary_join(self):
        self.assert_invalid(
            "SELECT d.icd_code FROM diagnoses_icd d "
            "JOIN d_icd_diagnoses di ON d.icd_code = di.icd_code"
        )
        self.assert_valid(
            "SELECT d.icd_code FROM diagnoses_icd d "
            "JOIN d_icd_diagnoses di ON d.icd_code = di.icd_code "
            "AND d.icd_version = di.icd_version"
        )


if __name__ == "__main__":
    unittest.main()
