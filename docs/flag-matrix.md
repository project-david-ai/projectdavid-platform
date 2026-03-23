# ProjectDavid Platform — Flag Matrix

| Service | _(none)_ | `--ollama` | `--vllm` | `--gpu` | `--training` | `--training --vllm` | `--gpu --training` |
|---|---|---|---|---|---|---|---|
| db, redis, qdrant, searxng, browser, otel, jaeger, samba, nginx | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| api | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| sandbox | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| ollama | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ✅ |
| vllm (static) | ❌ | ❌ | ✅ | ✅ | ❌ | ✅ | ✅ |
| training-api | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| training-worker | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| Ray cluster | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| vLLM dynamic spawning | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |

## Notes

- `--training` alone is fully self-contained. The training-worker spawns vLLM
  containers dynamically via Docker SDK — it does not depend on the static
  `vllm` compose service.

- `--training --vllm` adds the static always-on vLLM instance alongside the
  dynamic mesh-managed one. Valid for advanced use cases.

- `--gpu --training` is the full sovereign stack — Ollama + static vLLM +
  training pipeline + Ray cluster.

- Adding a flag to a running stack is safe. Docker Compose merges overlays
  and only starts new services, leaving existing containers untouched.