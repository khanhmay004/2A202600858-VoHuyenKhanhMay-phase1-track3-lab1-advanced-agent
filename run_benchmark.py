from __future__ import annotations
import json
from pathlib import Path
import typer
from rich import print
from src.reflexion_lab.agents import ReActAgent, ReflexionAgent
from src.reflexion_lab.mock_runtime import set_mode
from src.reflexion_lab.reporting import build_report, save_report
from src.reflexion_lab.utils import load_dataset, save_jsonl
app = typer.Typer(add_completion=False)


def _run_all(agent, examples, label):
    records = []
    total = len(examples)
    for i, example in enumerate(examples, 1):
        records.append(agent.run(example))
        if i % 10 == 0 or i == total:
            print(f"[dim]{label}: {i}/{total}[/dim]")
    return records


@app.command()
def main(
    dataset: str = "data/hotpot_mini.json",
    out_dir: str = "outputs/sample_run",
    reflexion_attempts: int = 3,
    mode: str = typer.Option("mock", help="'mock' (offline, free) or 'llm' (calls OpenAI)."),
    limit: int = typer.Option(0, help="Cap the number of questions (0 = use all)."),
) -> None:
    set_mode(mode)
    examples = load_dataset(dataset)
    if limit and limit > 0:
        examples = examples[:limit]
    print(f"[bold]Mode:[/bold] {mode} | [bold]Questions:[/bold] {len(examples)} | [bold]Reflexion attempts:[/bold] {reflexion_attempts}")
    react = ReActAgent()
    reflexion = ReflexionAgent(max_attempts=reflexion_attempts)
    react_records = _run_all(react, examples, "react")
    reflexion_records = _run_all(reflexion, examples, "reflexion")
    all_records = react_records + reflexion_records
    out_path = Path(out_dir)
    save_jsonl(out_path / "react_runs.jsonl", react_records)
    save_jsonl(out_path / "reflexion_runs.jsonl", reflexion_records)
    report = build_report(all_records, dataset_name=Path(dataset).name, mode=mode)
    json_path, md_path = save_report(report, out_path)
    print(f"[green]Saved[/green] {json_path}")
    print(f"[green]Saved[/green] {md_path}")
    print(json.dumps(report.summary, indent=2))


if __name__ == "__main__":
    app()
