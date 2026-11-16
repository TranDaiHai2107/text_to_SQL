# MIMIC-IV v3.1 clinical catalog export

**Export code and synthetic validation complete. Real export awaits approval.**
The catalog command uses four SELECTs bound to the verified schema manifest
and reader executor. The projections are fixed in `catalog_export.py`.

- `d_icd_diagnoses`, `d_icd_procedures` supply exact ICD code strings,
  ICD version and long title.
- `d_labitems` supplies itemid, label, fluid and category.
- `d_items` supplies itemid, label, abbreviation, source event table, unit
  and category.

The export sorts dictionary keys for reproducible output, includes source,
MIMIC version, format version, authorization reference and schema SHA-256,
and reports the file SHA-256. It uses no patient event tables, gold files or
generated aliases. The loader validates the export before it can enter
clinical retrieval. The fake BigQuery client tested code strings with leading
zeroes, ICD versions and item metadata against the real SQL Guard and loader.
An incomplete dictionary result fails before the output file is written.

```powershell
py -3 run.py four-method-pilot plan --method catalog_export --variant local_dictionary
py -3 run.py four-method-pilot export-catalog --approval <dictionary-approval.json> --sql-budget <dictionary-sql.json> --credit <credit.json> --destination mimiciv_3_1_catalog_v1.json
```

The plan prints exact SQL without submitting it. The export needs a
dictionary-only reader approval, an authorized local storage policy and
enough row/result-byte capacity for the largest dictionary. Its output is
created under `results/restricted/four_method_pilot/catalog`. Permission to
send approved dictionary metadata to GPT-5-mini is separate from local export.
