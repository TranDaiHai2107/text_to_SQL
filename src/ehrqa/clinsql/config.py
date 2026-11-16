"""Central BigQuery connection configuration; importing never connects."""
from __future__ import annotations

from dataclasses import dataclass
import os
import re


@dataclass(frozen=True)
class BigQueryConfig:
    project_id: str
    hosp_dataset: str
    icu_dataset: str
    location: str
    billing_project: str

    def __post_init__(self):
        for value in (self.project_id, self.hosp_dataset, self.icu_dataset,
                      self.billing_project):
            if not re.fullmatch(r'[A-Za-z0-9_-]+', value):
                raise ValueError('Invalid BigQuery project/dataset identifier')
        if not self.location.strip():
            raise ValueError('BigQuery location is required')

    @classmethod
    def from_env(cls):
        names = ('BQ_PROJECT_ID', 'BQ_HOSP_DATASET', 'BQ_ICU_DATASET',
                 'BQ_LOCATION', 'BQ_BILLING_PROJECT')
        missing = [name for name in names if not os.environ.get(name)]
        if missing:
            raise ValueError('Missing BigQuery configuration: ' + ', '.join(missing))
        return cls(*(os.environ[name] for name in names))

    @property
    def allowed_datasets(self) -> tuple[str, str]:
        return (f'{self.project_id}.{self.hosp_dataset}',
                f'{self.project_id}.{self.icu_dataset}')


@dataclass(frozen=True)
class ExperimentConfig:
    """One SQL-generating model configuration shared by all four methods."""
    model_id: str = 'gpt-5-mini'
    model_snapshot: str | None = None
    temperature: float | None = None
    max_output_tokens: int = 4096

    def __post_init__(self):
        if not self.model_id or self.max_output_tokens <= 0:
            raise ValueError('Valid common model configuration required')
