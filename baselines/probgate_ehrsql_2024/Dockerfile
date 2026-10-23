FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Offline cached replay/scoring uses only the Python standard library.
# Do not install the author's training environment or bake datasets/API keys in.
RUN groupadd --gid 10001 baseline \
    && useradd --uid 10001 --gid baseline --no-create-home baseline

COPY baseline_core.py reproduce.py docker_runner.py source_manifest.json ./
COPY configs ./configs

USER 10001:10001

ENTRYPOINT ["python", "-u", "docker_runner.py"]
CMD ["serve"]
