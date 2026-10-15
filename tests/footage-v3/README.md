# Isolated footage V3 checks

The normal application remains a Windows desktop application. This container is optional test infrastructure, with no profile, keys, Docker socket or source-media mounts. Build from the repository root:

```sh
docker build -f tests/footage-v3/Dockerfile -t newsflow-footage-v3-tests .
docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges newsflow-footage-v3-tests
docker run --rm --network none --cap-drop ALL --security-opt no-new-privileges -e NEWSFLOW_FOOTAGE_MEDIA_OUTPUT=/results/media newsflow-footage-v3-tests python tests/run_isolated.py --pytest tests/test_footage_v3_media.py -q
```

Python dependencies use the repository hash-locked requirements. The Python base tag is versioned; Debian FFmpeg/Tk packages depend on the build-time Debian repository. Record the resulting image digest and installed package versions for an actual reproducible acceptance run. The configuration has not been built or run while Docker Desktop's engine pipe is unavailable. A future clean build may expose platform-specific dependency issues; this is NOT a Docker PASS.

Local source checks always use `python tests/run_isolated.py --pytest ...`. Opt-in runs:

- `NEWSFLOW_FOOTAGE_BENCHMARK=<local-json-path>` with `tests/test_footage_v3_benchmark.py`: five repeats at 1k/10k/20k and 12/72 queries. Synthetic vectors and mocked file existence; no real visual semantics or disk/decode timing.
- `NEWSFLOW_FOOTAGE_DIVERSITY=<local-json-path>` with `tests/test_footage_v3_diversity.py`: suitable candidate pools, normal/fast, serial/parallel, sufficient/scarce cases. The fast setting remains a duration target for preparing the reuse pool, not a new definition of uniqueness.
- `NEWSFLOW_FOOTAGE_MEDIA_OUTPUT=<new-local-test-folder>` with `tests/test_footage_v3_media.py`: four actual source prepare/render/decode MP4s, synthetic patterns/metadata/embeddings and tone audio. These verify engineering transport only; named-person imagery and visual topical acceptance remain NOT VERIFIED.

No user footage is downloaded or included. Public evidence must be sanitized; full project paths and generated videos stay in ignored local test storage.

For BASE/AFTER media timing, use the **same FFmpeg executable** in both source checkouts. An archived Python-only checkout has no `assets/ffmpeg.exe` and will otherwise select the system binary, while the working Windows checkout selects its bundled binary. This invalidated the initial full-pipeline comparison. Copy the same repository-bundled test runtime into the disposable BASE checkout's `assets/` before comparing; verify SHA256 equality with `Get-FileHash`. Do not replace the application's actual binary or alter production settings. The media smoke now records Python/platform, FFmpeg version/hash and FFprobe version in its local manifest. Compare three alternating sequential BASE/AFTER runs, each through `run_isolated.py` with a new media output directory and fresh renderer cache; keep other test workloads stopped during timing. Reject comparisons with different runtime identities. Full source profiles remain local because they contain absolute paths.

`independent-ci.patch` adds the new regression suite to Linux CI and actual source Electron montage to Windows CI. GitHub rejected the original push because the current OAuth credential lacks `workflow` scope. The patch is preserved for the owner; active workflow files remain unchanged. Apply only through a workflow-authorized account. Existing PR CI still runs its current tests, but must not be represented as independent execution of the additional patch-only gates.
