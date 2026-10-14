# Test-only image. No application runtime, host profile, credentials or media mounts.
FROM python:3.12.10-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tk \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
COPY requirements-test.lock /workspace/requirements-test.lock
RUN python -m pip install --no-cache-dir --require-hashes -r requirements-test.lock
COPY scriptor /workspace/scriptor
COPY tests /workspace/tests
COPY pytest.ini /workspace/pytest.ini
ENV LOCALAPPDATA=/tmp/production-boundary NEWSFLOW_TEST_MODE=1 \
    NEWSFLOW_ENABLE_REAL_PROVIDERS=0 HF_HUB_OFFLINE=1
RUN useradd --create-home runner && mkdir -p /results && chown runner /results
USER runner
CMD ["python", "tests/run_isolated.py", "--pytest", "tests/test_footage_v3.py", "tests/test_ai_index.py", "tests/test_montage_semantic_diversity.py", "tests/test_montage_queue.py", "-q"]
