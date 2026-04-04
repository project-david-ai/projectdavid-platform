# Pinned Docker Images — Project David Platform

> **Last pinned:** 2026-04-04
> **Stack tested:** base + Sovereign Forge training profile
> **Method:** SHA256 digest — cryptographically immutable, tag-independent
> **Environment:** NVIDIA RTX 4060 Laptop GPU · CUDA 12.8 · Ubuntu (WSL2)

---

## Pinning Policy

Tags are mutable — a vendor can push a new image to the same tag silently.
Digests are immutable. Every image below is pinned to the exact layer that
was pulled, tested, and confirmed working on the date above.

When intentionally upgrading an image:
1. Pull the new version by tag
2. Run the full integration test suite
3. Capture the new digest:
   `docker inspect <image> --format '{{index .RepoDigests 0}}'`
4. Update this file and the compose files in the same commit
5. Bump `projectdavid-platform` version

---

## Third-Party Images (Base Stack)

| Service | Image | Pinned Tag | Current Stable | Digest | Notes |
|---------|-------|-----------|----------------|--------|-------|
| Reverse proxy | `nginx` | `alpine` | `stable-alpine3.23` | `sha256:e7257f1ef28ba17cf7c248cb8ccf6f0c6e0228ab9c315c152f9c203cd34cf6d1` | Digest confirmed current |
| Database | `mysql` | `8.0` | `8.0` | `sha256:64756cc92f707eb504496d774353990bcb0f6999ddf598b6ad188f2da66bd000` | Digest confirmed current |
| Cache / queue | `redis` | `7` | `7.4` | `sha256:a5995dfdf108997f8a7c9587f54fad5e94ed5848de5236a6b28119e99efd67e0` | Upgrade tag to 7.4 on next bump |
| Vector store | `qdrant/qdrant` | `latest` | `v1.17.0` | `sha256:94728574965d17c6485dd361aa3c0818b325b9016dac5ea6afec7b4b2700865f` | Upgrade tag to v1.17.0 on next bump |
| Browser automation | `ghcr.io/browserless/chromium` | `latest` | unknown | `sha256:57a1edb1f76e56cf1f128a2c379381df9d937e643c2cf562d76463b0280c24c4` | No semver tags published |
| Web search | `searxng/searxng` | `latest` | `2026.4.3-c980fa1ef` | `sha256:a89ed4a9dc2cbafeee79fc5fd75067e201543ed453fb43eae576d3e09c61780b` | Digest confirmed current |
| Telemetry collector | `otel/opentelemetry-collector-contrib` | `latest` | `v0.149.0` | `sha256:0fba96233274f6d665ac8831ad99dfe6479a9a20459f6e2719c0d20945773b46` | Upgrade tag to 0.149.0 on next bump |
| Tracing UI | `jaegertracing/all-in-one` | `latest` | `1.76.0` | `sha256:ab6f1a1f0fb49ea08bcd19f6b84f6081d0d44b364b6de148e1798eb5816bacac` | Upgrade tag to 1.76.0 on next bump |
| File share | `dperson/samba` | `latest` | N/A | `sha256:66088b78a19810dd1457a8f39340e95e663c728083efa5fe7dc0d40b2478e869` | Upstream inactive — evaluate replacement |

---

## Third-Party Images (GPU / Inference Profiles)

| Service | Image | Pinned Tag | Current Stable | Digest | Notes |
|---------|-------|-----------|----------------|--------|-------|
| Ollama inference | `ollama/ollama` | `latest` | `0.20.0` | `sha256:0455f166da85b1d07f694c33ba09278ca649603c0611ba8e46272b16eed7fccd` | Upgrade tag to 0.20.0 on next bump |
| vLLM inference | `vllm/vllm-openai` | `latest` | `v0.9.0` | `sha256:d9a5c1c1614c959fde8d2a4d68449db184572528a6055afdd0caf1e66fb51504` | Upgrade tag to v0.9.0 on next bump |

---

## First-Party Images (thanosprime/*)

Built and published by Project David CI. Pinned per platform release via
the release tag, not digest — they are rebuilt on every core push and
version-tracked through semantic-release.

| Service | Image |
|---------|-------|
| Core API | `thanosprime/projectdavid-core-api` |
| Sandbox | `thanosprime/projectdavid-core-sandbox` |
| Training API | `thanosprime/projectdavid-core-training-api` |
| Training Worker | `thanosprime/projectdavid-core-training-worker` |
| Inference Worker | `thanosprime/projectdavid-core-inference-worker` |

---

## Tag Upgrade Backlog

These images are pinned by digest but still pull under :latest or a major
version tag. On next intentional upgrade, replace with the specific stable
tag alongside the digest for full readability and immutability:

- [ ] qdrant/qdrant:latest -> qdrant/qdrant:v1.17.0@sha256:...
- [ ] redis:7 -> redis:7.4@sha256:...
- [ ] jaegertracing/all-in-one:latest -> jaegertracing/all-in-one:1.76.0@sha256:...
- [ ] otel/opentelemetry-collector-contrib:latest -> otel/opentelemetry-collector-contrib:0.149.0@sha256:...
- [ ] ollama/ollama:latest -> ollama/ollama:0.20.0@sha256:...
- [ ] vllm/vllm-openai:latest -> vllm/vllm-openai:v0.9.0@sha256:...
- [ ] searxng/searxng:latest -> searxng/searxng:2026.4.3-c980fa1ef@sha256:...
- [ ] Evaluate dperson/samba replacement (upstream inactive)
- [ ] Automate digest capture in CI on each platform release
