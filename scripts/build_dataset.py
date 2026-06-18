"""Convert the raw HotpotQA dev-distractor file into the QAExample format.

Usage (from project root, with the venv active):
    python scripts/build_dataset.py --src data/hotpot_dev_distractor_v1.json --out data/hotpot_100.json --n 120
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path

# HotpotQA "level" -> QAExample "difficulty". The dev-distractor set is labelled
# "hard" throughout; the map keeps any future easy/medium values intact.
LEVEL_MAP = {"easy": "easy", "medium": "medium", "hard": "hard"}


def convert(item: dict) -> dict:
    context = []
    for entry in item.get("context", []):
        # Real HotpotQA format: [title, [sentence, sentence, ...]].
        if isinstance(entry, (list, tuple)) and len(entry) == 2:
            title, sentences = entry
            text = " ".join(s.strip() for s in sentences)
        # Tolerate the dict variant: {"title": ..., "sentences": [...]}.
        elif isinstance(entry, dict):
            title = entry.get("title", "")
            text = " ".join(entry.get("sentences", []))
        else:
            continue
        context.append({"title": str(title), "text": text})
    return {
        "qid": item["_id"],
        "difficulty": LEVEL_MAP.get(item.get("level"), "medium"),
        "question": item["question"],
        "gold_answer": item["answer"],
        "context": context,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--src", default="data/hotpot_dev_distractor_v1.json")
    parser.add_argument("--out", default="data/hotpot_100.json")
    parser.add_argument("--n", type=int, default=120, help="Number of questions to take.")
    args = parser.parse_args()

    raw = json.loads(Path(args.src).read_text(encoding="utf-8"))
    examples = [convert(item) for item in raw[: args.n]]
    Path(args.out).write_text(json.dumps(examples, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(examples)} examples to {args.out}")


if __name__ == "__main__":
    main()
