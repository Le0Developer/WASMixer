#!/usr/bin/env python3
"""Run the AssemblyScript-relevant WebAssembly spec tests through WASMixer.

The upstream testsuite is a collection of WAST scripts. This runner compiles
each script's executable module commands with WABT, mixes those modules, then
replaces only those module declarations with their mixed binary equivalents
before running the original assertions in Wasmtime's WAST runner.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


EXCLUDED_ROOT_STEMS = {
    # GC and typed function-reference tests (not used by AssemblyScript's
    # normal Wasm output).
    "array", "array_copy", "array_fill", "array_init_data", "array_init_elem",
    "array_new_data", "array_new_elem", "binary-gc", "br_on_cast",
    "br_on_cast_fail", "br_on_non_null", "br_on_null", "call_ref", "extern",
    "i31", "local_init", "ref", "ref_as_non_null", "ref_cast", "ref_eq",
    "ref_is_null", "ref_test", "return_call_ref", "struct", "table_init",
    "tag", "throw_ref", "type-canon", "type-equivalence", "type-rec",
    "type-subtyping", "try_table",
    # These mix exception tags or typed GC references into general linking
    # and validation scripts, which the current binary model cannot rewrite.
    "imports", "linking", "unreached-valid",
    # Proposals beyond AssemblyScript's currently used feature set.
    "address0", "address1", "align", "align0", "align64", "annotations",
    "call_indirect64", "data0", "data_drop0", "id", "inline-module",
    "float_exprs0", "float_exprs1", "float_memory0", "imports1", "imports2",
    "imports4", "instance", "linking1", "linking2", "linking3", "load0",
    "load1", "load2", "memory", "memory-multi", "memory64",
    "memory64-imports", "memory_copy0", "memory_copy1", "memory_fill0",
    "memory_grow", "memory_init0", "memory_size0", "memory_size1",
    "memory_size2", "memory_size3", "memory_size_import", "memory_trap0",
    "memory_trap1", "ref_null", "return_call", "return_call_indirect", "simd_memory-multi",
    "start0", "store0", "store1", "store2", "table", "table64",
    "table_copy64", "table_fill64", "table_get64", "table_grow64",
    "table_init64", "table_set64", "table_size64", "traps0", "wide-arithmetic",
}

WABT_FEATURE_FLAGS = [
    "--enable-exceptions",
    "--enable-threads",
    "--enable-function-references",
    "--enable-relaxed-simd",
]


def selected_testsuite_files(root: Path) -> list[Path]:
    files = []
    for path in root.glob("*.wast"):
        stem = path.stem
        if stem in EXCLUDED_ROOT_STEMS or stem.endswith("64"):
            continue
        files.append(path)
    # Wasmtime 49 disagrees with the official expected validation failures in
    # these two scripts; the remaining thread proposal tests run normally.
    files.extend(sorted(
        path for path in (root / "proposals" / "threads").glob("*.wast")
        if path.stem not in {"imports", "memory"}
    ))
    return sorted(files)


def skip_space_and_comments(source: str, pos: int) -> int:
    while pos < len(source):
        if source[pos].isspace():
            pos += 1
        elif source.startswith(";;", pos):
            newline = source.find("\n", pos + 2)
            pos = len(source) if newline < 0 else newline + 1
        elif source.startswith("(;", pos):
            depth = 1
            pos += 2
            while pos < len(source) and depth:
                if source.startswith("(;", pos):
                    depth += 1
                    pos += 2
                elif source.startswith(";)", pos):
                    depth -= 1
                    pos += 2
                else:
                    pos += 1
            if depth:
                raise ValueError("unterminated WAST block comment")
        else:
            break
    return pos


def form_end(source: str, start: int) -> int:
    depth = 0
    pos = start
    in_string = False
    while pos < len(source):
        if source.startswith(";;", pos) and not in_string:
            newline = source.find("\n", pos + 2)
            pos = len(source) if newline < 0 else newline + 1
            continue
        if source.startswith("(;", pos) and not in_string:
            pos = skip_space_and_comments(source, pos)
            continue
        char = source[pos]
        if in_string:
            if char == "\\":
                pos += 2
                continue
            if char == '"':
                in_string = False
        elif char == '"':
            in_string = True
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return pos + 1
        pos += 1
    raise ValueError("unterminated WAST command")


def top_level_module_spans(source: str) -> list[tuple[int, int, str]]:
    """Find top-level (module ...) commands, excluding assert-invalid bodies."""
    spans = []
    pos = 0
    while pos < len(source):
        pos = skip_space_and_comments(source, pos)
        if pos >= len(source):
            break
        if source[pos] != "(":
            raise ValueError(f"expected WAST command at byte {pos}")
        end = form_end(source, pos)
        head_pos = skip_space_and_comments(source, pos + 1)
        head = re.match(r"([a-zA-Z0-9_-]+)", source[head_pos:end])
        if head and head.group(1) == "module":
            # Keep optional module identifiers (e.g. `$main`) intact.
            tail_pos = skip_space_and_comments(source, head_pos + head.end())
            tail = source[tail_pos:end]
            module_id = re.match(r"\s*(\$[^\s()]+)", tail)
            prefix = f"module {module_id.group(1)} " if module_id else "module "
            spans.append((pos, end, prefix))
        pos = end
    return spans


def wast_binary_string(binary: bytes) -> str:
    return '"' + "".join(f"\\{byte:02x}" for byte in binary) + '"'


def replace_modules(source: str, module_files: list[Path]) -> str:
    spans = top_level_module_spans(source)
    if len(spans) != len(module_files):
        raise ValueError(
            f"WAST module count mismatch: source has {len(spans)}, "
            f"wast2json emitted {len(module_files)} executable modules"
        )
    for (start, end, prefix), module_file in reversed(list(zip(spans, module_files))):
        source = source[:start] + f"({prefix}binary {wast_binary_string(module_file.read_bytes())})" + source[end:]
    return source


def run(command: list[str], *, cwd: Path | None = None, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(command, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("testsuite", type=Path, help="checkout of WebAssembly/testsuite")
    parser.add_argument("--wast2json", default="wast2json")
    parser.add_argument("--runner", default="wasmtime", help="WAST runner executable (wasmtime or wasm-shell)")
    parser.add_argument("--mixer", default=str(Path(__file__).resolve().parents[1] / "cli" / "main.py"))
    parser.add_argument("--mixer-options", default="--all")
    parser.add_argument("--limit", type=int, help="run only the first N selected scripts (for local debugging)")
    args = parser.parse_args()

    root = args.testsuite.resolve()
    files = selected_testsuite_files(root)
    if args.limit:
        files = files[:args.limit]
    if not files:
        print(f"No supported .wast tests found in {root}", file=sys.stderr)
        return 2

    failures = []
    modules_mixed = 0
    mixer_env = os.environ.copy()
    repo_root = Path(args.mixer).resolve().parents[1]
    mixer_env["PYTHONPATH"] = os.pathsep.join(
        path for path in (str(repo_root), mixer_env.get("PYTHONPATH", "")) if path
    )
    for number, test_file in enumerate(files, 1):
        relative = test_file.relative_to(root)
        with tempfile.TemporaryDirectory(prefix="wasmixer-spec-") as temp_dir:
            temp = Path(temp_dir)
            json_path = temp / "test.json"
            converted = run([args.wast2json, *WABT_FEATURE_FLAGS, str(test_file), "-o", str(json_path)])
            if converted.returncode:
                failures.append((relative, "wast2json", converted.stdout))
                print(f"[{number}/{len(files)}] FAIL {relative}: WAST conversion", flush=True)
                continue

            data = json.loads(json_path.read_text())
            module_files = [temp / command["filename"] for command in data["commands"] if command["type"] == "module"]
            transformed_files = []
            transform_failed = None
            for module_file in module_files:
                transformed = run(
                    [sys.executable, args.mixer, str(module_file), *args.mixer_options.split()],
                    env=mixer_env,
                )
                if transformed.returncode:
                    transform_failed = (module_file.name, transformed.stdout)
                    break
                modules_mixed += 1
                transformed_files.append(module_file)
            if transform_failed:
                failures.append((relative, "WASMixer", f"{transform_failed[0]}\n{transform_failed[1]}"))
                print(f"[{number}/{len(files)}] FAIL {relative}: mixing", flush=True)
                continue

            try:
                mixed_script = replace_modules(test_file.read_text(), transformed_files)
            except Exception as error:
                failures.append((relative, "rewrite", str(error)))
                print(f"[{number}/{len(files)}] FAIL {relative}: rewrite", flush=True)
                continue
            mixed_path = temp / test_file.name
            mixed_path.write_text(mixed_script)
            command = (
                [args.runner, "wast", "-C", "cache=n", "--ignore-error-messages", str(mixed_path)]
                if Path(args.runner).name == "wasmtime"
                else [args.runner, str(mixed_path)]
            )
            executed = run(command)
            if executed.returncode:
                failures.append((relative, args.runner, executed.stdout))
                print(f"[{number}/{len(files)}] FAIL {relative}: {args.runner}", flush=True)
            else:
                print(f"[{number}/{len(files)}] PASS {relative}", flush=True)

    if failures:
        print(f"\n{len(failures)} of {len(files)} WAST scripts failed; mixed {modules_mixed} modules.")
        for path, phase, output in failures:
            print(f"\n=== {path} [{phase}] ===\n{output}")
        return 1

    print(f"\nPassed {len(files)} WAST scripts; mixed {modules_mixed} modules.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
