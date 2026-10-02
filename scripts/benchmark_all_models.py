"""
Benchmark every transformer model in BERT_MODEL_REGISTRY on CPU and (if
available) GPU, and print a comparison table. This is the source of the
numbers quoted in README/AGENTS and in the admin UI model descriptions -
it explains why the larger OpenMed models are marked "GPU empfohlen".

Usage:
    uv run python scripts/benchmark_all_models.py                 # all models, CPU + GPU
    uv run python scripts/benchmark_all_models.py --no-gpu        # CPU only
    uv run python scripts/benchmark_all_models.py transformer_ner_fhswf

Each model/device combination runs in a fresh subprocess (via the existing
scripts/benchmark_bert_recognizer.py) so models never share the module-level
cache or VRAM/RAM - a large model is unloaded again when its run ends. The
first run of a model downloads it from HuggingFace (~180 MB to ~1.7 GB).
"""

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from backend.components.bert_recognizer import BERT_MODEL_REGISTRY, gpu_available  # noqa: E402

RUNNER = PROJECT_ROOT / "scripts" / "benchmark_bert_recognizer.py"

MEAN_RE = re.compile(r"mean=([\d.]+)ms median=([\d.]+)ms")
INIT_RE = re.compile(r"analyzer init \(incl\. model load if enabled\): ([\d.]+)s")


def run_one(model_name: str, device: str) -> dict:
    """Run the single-model benchmark in a subprocess and parse its summary."""
    env = os.environ.copy()
    env["BERT_NER_MODEL"] = model_name
    env["BERT_NER_DEVICE"] = device

    proc = subprocess.run(
        [sys.executable, str(RUNNER)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    output = proc.stdout + proc.stderr
    if proc.returncode != 0:
        return {"ok": False, "error": output.strip().splitlines()[-1] if output.strip() else "unknown error"}

    means = MEAN_RE.findall(output)
    if len(means) < 2:
        return {"ok": False, "error": "could not parse benchmark output"}

    baseline_mean, baseline_median = (float(x) for x in means[0])
    model_mean, model_median = (float(x) for x in means[-1])
    init = INIT_RE.findall(output)
    init_s = float(init[-1]) if init else float("nan")

    return {
        "ok": True,
        "baseline_mean": baseline_mean,
        "baseline_median": baseline_median,
        "mean": model_mean,
        "median": model_median,
        "init_s": init_s,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument(
        "models",
        nargs="*",
        help="registry keys to benchmark (default: all in BERT_MODEL_REGISTRY)",
    )
    parser.add_argument("--no-gpu", action="store_true", help="skip GPU runs")
    args = parser.parse_args()

    keys = args.models or list(BERT_MODEL_REGISTRY.keys())
    unknown = [k for k in keys if k not in BERT_MODEL_REGISTRY]
    if unknown:
        parser.error(f"unknown model key(s): {unknown}")

    devices = ["cpu"]
    if not args.no_gpu and gpu_available():
        devices.append("cuda")

    print("EntityGuard transformer model benchmark")
    print(f"devices: {', '.join(devices)}\n")

    results: dict[tuple[str, str], dict] = {}
    baseline = None
    for key in keys:
        model_name = str(BERT_MODEL_REGISTRY[key]["model"])
        gpu_flag = " (GPU empfohlen)" if BERT_MODEL_REGISTRY[key].get("gpu_recommended") else ""
        for device in devices:
            print(f"--> {key} @ {device}{gpu_flag}  ({model_name})", flush=True)
            res = run_one(model_name, device)
            results[(key, device)] = res
            if res["ok"]:
                baseline = res["baseline_mean"]
                print(
                    f"    init {res['init_s']:.1f}s | mean {res['mean']:.1f}ms "
                    f"median {res['median']:.1f}ms"
                )
            else:
                print(f"    FAILED: {res['error']}")

    print("\n" + "=" * 78)
    if baseline is not None:
        print(f"Baseline (spaCy + DB patterns, no transformer): {baseline:.1f}ms\n")

    header = f"{'Model':34s} {'Device':6s} {'Init':>6s} {'Mean':>9s} {'Median':>9s} {'Speedup':>8s}"
    print(header)
    print("-" * len(header))

    for key in keys:
        gpu_flag = " *" if BERT_MODEL_REGISTRY[key].get("gpu_recommended") else ""
        cpu_mean = results.get((key, "cpu"), {}).get("mean")
        for device in devices:
            res = results.get((key, device), {})
            label = key + gpu_flag if device == devices[0] else ""
            if not res.get("ok"):
                print(f"{label:34s} {device:6s} {'--':>6s} {'FAILED':>9s}")
                continue
            speedup = ""
            if device == "cuda" and cpu_mean:
                speedup = f"{cpu_mean / res['mean']:.1f}x"
            print(
                f"{label:34s} {device:6s} {res['init_s']:5.1f}s "
                f"{res['mean']:8.1f}ms {res['median']:8.1f}ms {speedup:>8s}"
            )

    print("\n* = GPU empfohlen in der Admin-UI (CPU-Betrieb ist deutlich langsamer).")
    print("Zum Aktualisieren der Doku diese Tabelle in README/AGENTS übernehmen.")


if __name__ == "__main__":
    main()