# Project David Platform

[![Docker Pulls](https://img.shields.io/docker/pulls/thanosprime/entities-api-api?label=API%20Pulls&logo=docker&style=flat-square)](https://hub.docker.com/r/thanosprime/entities-api-api)
[![CI](https://github.com/project-david-ai/platform-docker/actions/workflows/ci.yml/badge.svg)](https://github.com/project-david-ai/platform-docker/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/projectdavid-platform?style=flat-square)](https://pypi.org/project/projectdavid-platform/)
[![License: PolyForm Noncommercial](https://img.shields.io/badge/license-PolyForm%20Noncommercial%201.0.0-blue.svg)](https://polyformproject.org/licenses/noncommercial/1.0.0/)

Deployment orchestrator for the Project David / Entities platform. Provides a single command to bring up the complete infrastructure stack, including database, vector store, search, observability, secure code execution, and optional GPU inference services.

---

## Installation

```bash
pip install projectdavid-platform
```

No repository clone required. The compose files and configuration templates are bundled with the package.

---

## Quick Start

```bash
platform --mode up
```

On first run this will:

- Generate a `.env` file with unique, cryptographically secure secrets
- Prompt for optional values (HuggingFace token for gated model access)
- Pull all required Docker images
- Start the full stack in detached mode

### GPU stack (vLLM + Ollama)

```bash
platform --mode up --gpu
```

Requires an NVIDIA GPU with the [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html) installed.

---

## Stack Services

| Service | Image | Description |
|---|---|---|
| `api` | `thanosprime/entities-api-api` | FastAPI backend exposing assistant and inference endpoints |
| `sandbox` | `thanosprime/entities-api-sandbox` | Secure code execution environment |
| `db` | `mysql:8.0` | Relational persistence |
| `qdrant` | `qdrant/qdrant` | Vector database for embeddings and RAG |
| `redis` | `redis:7` | Cache and message broker |
| `searxng` | `searxng/searxng` | Self-hosted web search |
| `browser` | `browserless/chromium` | Headless browser for web agent tooling |
| `otel-collector` | `otel/opentelemetry-collector-contrib` | Telemetry collection |
| `jaeger` | `jaegertracing/all-in-one` | Distributed tracing UI |
| `samba` | `dperson/samba` | File sharing for uploaded documents |
| `ollama` | `ollama/ollama` | Local LLM inference (GPU stack only) |
| `vllm` | `vllm/vllm-openai` | High-throughput GPU inference (GPU stack only) |

---

## Prerequisites

- Docker and Docker Compose
- Python 3.9 or later
- NVIDIA GPU with NVIDIA Container Toolkit (GPU stack only)

---

## Lifecycle Commands

### Start the stack

```bash
platform --mode up
```

### Start with GPU services

```bash
platform --mode up --gpu
```

### Stop the stack

```bash
platform --mode down_only
```

### Stop and remove all volumes

```bash
platform --mode down_only --clear-volumes
```

### Force recreate all containers

```bash
platform --mode up --force-recreate
```

### Stream logs

```bash
platform --mode logs --follow
```

### Destroy all stack data

```bash
platform --nuke
```

Requires interactive confirmation. Cannot be undone.

---

## Configuration

### Setting optional values

Optional values such as the HuggingFace token can be set at any time without regenerating secrets:

```bash
platform configure --set HF_TOKEN=hf_abc123
platform configure --set VLLM_MODEL=Qwen/Qwen2.5-VL-7B-Instruct
```

Or interactively:

```bash
platform configure --interactive
```

### Rotating secrets

The orchestrator warns when a change requires additional steps to apply safely. Database password rotation requires clearing the initialised volume:

```bash
platform configure --set MYSQL_PASSWORD=<new_password>
# Follow the warning instructions printed by the command
```

---

## Post-startup Provisioning

Once the stack is running, provision the admin user and default assistant:

```bash
# Bootstrap the default admin user
platform bootstrap-admin

# Create a regular user
platform create-user --email user@example.com --name "Alice"

# Set up the default assistant
platform setup-assistant --api-key ad_... --user-id usr_...
```

Full provisioning walkthrough: [`docs/boot_strap.md`](docs/boot_strap.md)

---

## Docker Images

Both owned images are published to Docker Hub and updated automatically on each release of the source repository.

- [thanosprime/entities-api-api](https://hub.docker.com/r/thanosprime/entities-api-api)
- [thanosprime/entities-api-sandbox](https://hub.docker.com/r/thanosprime/entities-api-sandbox)

---

## Related Repositories

| Repository | Purpose |
|---|---|
| [entities_api](https://github.com/frankie336/entities_api) | FastAPI backend source code, inference engine, and tooling framework |
| [projectdavid](https://github.com/frankie336/projectdavid) | Python SDK for interacting with the Entities API |
| [platform-docker](https://github.com/project-david-ai/platform-docker) | This repository — deployment orchestration |

---

## Working with the Source Code

This repository is intended for deploying prebuilt images. To develop, extend, or contribute to the platform source:

```bash
git clone https://github.com/frankie336/entities_api.git
cd entities_api
pip install -e .
entities-api docker-manager --mode up
```

---

## License

Distributed under the [PolyForm Noncommercial License 1.0.0](https://polyformproject.org/licenses/noncommercial/1.0.0/).
Commercial licensing is available on request.