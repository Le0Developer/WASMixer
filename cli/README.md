# WASMixer (CLI)
## Install dependencies
**Requirements**
- Python `>= 3.9`
**Install**
```bash
cd WASMixer #root of repository
python -m pip install -e .
```
## Usage
```sh
cd cli
python main.py <wasm_file> [options]
```

### Options
- `<wasm_file>`: Path to the input `.wasm` file to obfuscate (required unless using `--list`).
- `--flatten`: Apply control flow flattening.
- `--alias`: Apply alias disruption.
- `--name`: Apply name obfuscation.
- `--memory`: Apply memory obfuscation.
- `--collatz` : Apply Collatz transformation on all applicable obfuscations")
    - `--cf` : Collatz transformation on flattening
    - `--ca` : Collatz transformation on alias disruption
- `--all`: Apply all obfuscation levels.
- `--safe`: Do not overwrite the original file; process a copy named `<name>_mixr.wasm`.
- `--seed`: Set the seed used by the final semantics-preserving code mutation pass.
- `--list`: List available obfuscation levels and exit.

### Examples

List all available obfuscation levels:
```sh
python main.py --list
```

Obfuscate a binary with control flow flattening and alias disruption:
```sh
python main.py mybinary.wasm --flatten --alias
```

Obfuscate a binary with all levels, overwriting the original:
```sh
python main.py mybinary.wasm --all
```

Obfuscate a binary with all levels, keeping the original safe:
```sh
python main.py mybinary.wasm --all --safe
```

### Notes
- If you use `--safe`, the original file is copied to `<name>_mixr.wasm` and only the copy is modified.
- Without `--safe`, the original file **is overwritten.**
- The current mutation pass has experimental SSA for mutable locals over structured control flow. Its instruction scheduler still handles only self-contained integer expression regions; it does not yet convert operand-stack values or lower general phi nodes back to Wasm.
- Make sure WASMixer is installed in editable mode and all dependencies are satisfied.

For more details, see the docstrings in `main.py`.
