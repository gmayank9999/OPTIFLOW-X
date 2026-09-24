"""Compiles each benchmark program at -O0 and saves its outputs as the reference.

Run once, before any experiments start. Never regenerate after that point,
or accepted/rejected candidates from earlier runs stop being comparable.

Compilation happens in a scratch temp directory, never inside benchmarks/,
so this script only ever writes to each program's expected/ folder.
"""

import json
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).parent
sys.path.insert(0, str(ROOT.parent))

from optiflow.tools.sandbox import run_in_sandbox  # noqa: E402


def compile_o0(scratch_dir: pathlib.Path, lang: str) -> None:
    src_name = "main.c" if lang == "c" else "main.cpp"
    cc = "gcc" if lang == "c" else "g++"
    result = run_in_sandbox(str(scratch_dir), f"{cc} -O0 -g {src_name} -o prog -lm", timeout_s=60)
    if result["exit"] != 0:
        raise RuntimeError(f"compile failed in {scratch_dir}: {result['stderr']}")


def run_input(scratch_dir: pathlib.Path, program_dir: pathlib.Path, input_rel: str, timeout_s: int) -> str:
    input_path = program_dir / input_rel
    dest = scratch_dir / input_path.name
    dest.write_bytes(input_path.read_bytes())
    result = run_in_sandbox(str(scratch_dir), f"./prog < {input_path.name}", timeout_s=timeout_s)
    if result["exit"] != 0:
        raise RuntimeError(f"run failed for {program_dir.name} on {input_rel}: {result['stderr']}")
    return result["stdout"]


def main() -> None:
    manifest = json.loads((ROOT / "manifest.json").read_text())
    for entry in manifest["programs"]:
        program_id = entry["id"]
        program_dir = ROOT / program_id
        meta = json.loads((program_dir / "meta.json").read_text())
        src_name = "main.c" if meta["language"] == "c" else "main.cpp"

        scratch_dir = pathlib.Path(tempfile.mkdtemp(prefix=f"expected_{program_id}_"))
        try:
            shutil.copy(program_dir / src_name, scratch_dir / src_name)
            compile_o0(scratch_dir, meta["language"])

            for in_rel, out_rel in zip(meta["inputs"], meta["expected"]):
                output = run_input(scratch_dir, program_dir, in_rel, meta.get("timeout_s", 20))
                out_path = program_dir / out_rel
                out_path.parent.mkdir(exist_ok=True)
                out_path.write_text(output)
                print(f"{program_id}: {in_rel} -> {out_rel} ({len(output)} bytes)")
        finally:
            shutil.rmtree(scratch_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
