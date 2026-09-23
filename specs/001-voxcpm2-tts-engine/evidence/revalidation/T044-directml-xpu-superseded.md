# Superseded: T044 quickstart Step 5, DirectML and Intel XPU

`evidence/phase7/T044-quickstart.txt` recorded Step 5 as PASS. With the detector forced to DirectML or Intel XPU, VoxCPM2 was reported unavailable and `/generate` returned 400 (lines ~651-659 there).

The analyze revalidation (finding H1, 2026-09-23) found that this contradicts FR-023. VoxCPM2 declares `cpu`, and its backend picks its own device without XPU or DirectML, so on those machines it really runs on the processor.

After the H1 fix in `backend/backends/base.py` (`resolve_engine_availability`), the behaviour on those machines is:
- VoxCPM2 is available.
- `reason` is null.
- `warning` reads "VoxCPM2 (Multilingual, Voice Design) doesn't support DirectML here, so it will run on the processor, which is slower." (Intel XPU gives the same text with its own label.)
- `detected_accelerator` still shows the real accelerator.
- Every generation entry point proceeds: generate, stream, retry, regenerate, speak and MCP speak.

An engine that does not declare `cpu` is still refused with a 400 and a reason.

Evidence:
- `H1-red.xml` (tests=402, failures=30)
- `H1-green.xml` (tests=544, failures=0)
- `orch-H1.xml` (orchestrator re-run, 544/0)
- `orch-full-suite.xml` (tests=1069, failures=1 baseline `test_hf_progress_tracker`, skipped=9)

The other T044 results still stand: Steps 1-4, 6 and 7, CUDA, CPU, and the memory warning.
