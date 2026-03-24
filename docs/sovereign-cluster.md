# Sovereign Forge — Training + Inference Mesh

Sovereign Forge is the opt-in training pipeline built into ProjectDavid. It turns
spare GPU hardware into a private fine-tuning and inference cluster — your data
stays on your machines, the models you train run on your hardware, and the
resulting endpoints are served through the same API surface as any other inference
provider in the stack.

## Requirements

- NVIDIA GPU with drivers installed
- [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/install-guide.html)
- Docker socket accessible at `/var/run/docker.sock`
- HuggingFace token for gated model downloads (optional but recommended)

## Starting the training stack

```bash
# Training pipeline + Ray cluster only
pdavid --mode up --training

# Training pipeline + static vLLM inference server
pdavid --mode up --training --vllm

# Full sovereign stack — Ollama + vLLM + training pipeline
pdavid --mode up --gpu --training
```

Adding `--training` to a running stack is safe. Docker Compose merges the overlay
and only starts the new services — existing containers are untouched.

## What gets added

| Service | Port | Purpose |
|---|---|---|
| `training-api` | `9001` | REST API for datasets, training jobs, and model registry |
| `training-worker` | — | GPU worker, Ray head node, DeploymentSupervisor actor |
| Ray dashboard | `8265` | Cluster visibility — http://localhost:8265 |
| Ray client | `10001` | External node join protocol |

The `training-worker` also spawns vLLM containers dynamically via the Docker SDK
when models are activated — this is independent of the static `--vllm` service.

## Configuration

On first run with `--training`, the orchestrator injects any missing variables
into your existing `.env` without touching secrets or other values:

```
TRAINING_PROFILE=laptop     # laptop | standard | high_end
RAY_ADDRESS=                # blank = head node; set to ray://<ip>:10001 to join
RAY_DASHBOARD_PORT=8265
```

Update them at any time:

```bash
pdavid configure --set TRAINING_PROFILE=standard
pdavid configure --set HF_TOKEN=hf_abc123
```

## Scaling out — adding a second GPU node

On any machine with a GPU and the NVIDIA Container Toolkit:

1. Set `RAY_ADDRESS=ray://<head_ip>:10001` in `.env`
2. Run:
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.training.yml up -d training-worker
   ```

Ray discovers the node automatically. Cluster capacity increases immediately.
No code changes required.

## Activating a model for inference

Once the training stack is running, use the ProjectDavid SDK:

```python
import projectdavid as pd

client = pd.Client()

# Deploy a base model (single GPU)
client.models.activate_base("unsloth/qwen2.5-1.5b-instruct-unsloth-bnb-4bit")

# Deploy across multiple GPUs (tensor parallelism)
client.models.activate_base(
    "unsloth/Qwen2.5-7B-Instruct",
    tensor_parallel_size=4
)

# Deploy a fine-tuned LoRA adapter
client.models.activate("ftm_abc123")
```

The deployment is scheduled by Ray, the vLLM container is spawned dynamically,
and the InferenceResolver routes requests to the correct endpoint automatically.