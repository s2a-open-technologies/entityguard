"""
.
Copyright (C) 2026  Christopher Abanilla

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU Affero General Public License as
published by the Free Software Foundation, either version 3 of the
License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License
along with this program.  If not, see <https://www.gnu.org/licenses/>.

Benchmark CustomAnalyzer.process_text() latency with the BERT NER
recognizer (native PyTorch, GPU if available) disabled vs enabled. Run with:

    BERT_NER_MODEL=xlm-roberta-large-finetuned-conll03-german \
        uv run python scripts/benchmark_bert_recognizer.py
"""

import os
import sys
import time
from pathlib import Path
from statistics import mean, median

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

SAMPLE_TEXTS = [
    "Herr Max Mustermann wohnhaft in der Musterstraße 12, 12345 Musterstadt, "
    "wurde am 03.01.2026 in der Charité Berlin von Dr. Anna Schmidt behandelt.",
    "Die Patientin Erika Beispiel arbeitet bei der Deutsche Bahn AG in München "
    "und ist unter erika.beispiel@example.com erreichbar.",
    "Bitte kontaktieren Sie Herrn Prof. Dr. Klaus Weber, Universitätsklinikum "
    "Hamburg-Eppendorf, telefonisch unter 040 1234567.",
]

N_RUNS = 5


def _run(label: str, bert_enabled: bool) -> None:
    os.environ["BERT_NER_ENABLED"] = "true" if bert_enabled else "false"

    # _get_bert_recognizer() re-reads this env var on every CustomAnalyzer
    # init, so toggling it between calls in the same process works as
    # expected (the model is only ever loaded once, on first enabled call).
    from src.components.cstm_analyzer import CustomAnalyzer

    load_start = time.perf_counter()
    analyzer = CustomAnalyzer(language="de", db=None)
    load_elapsed = time.perf_counter() - load_start
    print(f"\n[{label}] analyzer init (incl. model load if enabled): {load_elapsed:.2f}s")

    durations = []
    for _ in range(N_RUNS):
        for text in SAMPLE_TEXTS:
            start = time.perf_counter()
            analyzer.process_text(text)
            durations.append((time.perf_counter() - start) * 1000)

    print(
        f"[{label}] process_text over {len(durations)} calls: "
        f"mean={mean(durations):.1f}ms median={median(durations):.1f}ms "
        f"min={min(durations):.1f}ms max={max(durations):.1f}ms"
    )


if __name__ == "__main__":
    _run("baseline (spaCy + DB recognizers only)", bert_enabled=False)
    _run("with BertNerRecognizer (native torch, GPU)", bert_enabled=True)
