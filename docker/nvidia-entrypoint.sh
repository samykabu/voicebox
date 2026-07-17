#!/bin/sh
set -eu

# Docker named volumes are normally initialized with the ownership baked into
# the image. Repair ownership as root as well, which covers volumes created by
# older Voicebox images, then drop privileges before starting the API server.
mkdir -p \
    /app/data/generations \
    /app/data/profiles \
    /app/data/cache \
    /home/voicebox/.cache/huggingface \
    /home/voicebox/.cache/torch \
    /tmp/numba_cache

voicebox_owner="$(id -u voicebox):$(id -g voicebox)"
for directory in /app/data /home/voicebox/.cache /tmp/numba_cache; do
    if [ "$(stat -c '%u:%g' "$directory")" != "$voicebox_owner" ]; then
        chown -R voicebox:voicebox "$directory"
    fi
done

# This is the CUDA-only overlay: never silently run its multi-gigabyte ML stack
# on the CPU when GPU passthrough is missing or misconfigured.
python - <<'PY'
import sys

import torch

if not torch.cuda.is_available():
    print(
        "ERROR: NVIDIA CUDA is unavailable inside the Voicebox container. "
        "Check the host driver, NVIDIA Container Toolkit/Docker Desktop GPU "
        "support, and docker-compose.cuda.yml device reservation.",
        file=sys.stderr,
    )
    raise SystemExit(1)

count = torch.cuda.device_count()
print(f"Voicebox CUDA ready: PyTorch {torch.__version__}, CUDA {torch.version.cuda}, {count} visible GPU(s)")
for index in range(count):
    props = torch.cuda.get_device_properties(index)
    capability = torch.cuda.get_device_capability(index)
    print(
        f"  cuda:{index}: {props.name} "
        f"(compute {capability[0]}.{capability[1]}, {props.total_memory / 1024**3:.1f} GiB)"
    )
PY

exec gosu voicebox "$@"
