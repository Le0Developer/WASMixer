# WASMixer

WASMixer consists of two main functions: the data obfuscator and the code obfuscator. The data obfuscator randomizes readable names and encrypts/decrypts memory areas at runtime. The code obfuscator manipulates instructions and control flow through techniques like alias disruption, control flow flattening, and Collatz-based opaque predicates. Flattened functions also contain a runtime-dependent guard around dead arithmetic code; its parity predicate is always false for 32-bit values.

## Getting Started

### Docker

1.   set environment

The Docker image is based on Alpine Linux 3.24.
Please download [Docker](https://docs.docker.com/get-docker/) first.
```bash
sudo docker build -t wasmixer .
sudo docker run -it wasmixer # run a docker container
```

2. obfuscate the wasm binaries in our collected benchmarks

```bash
# in the docker container
cd example
python3 obfuscate_benchmark.py
```

### CLI

See [details here](./cli/README.md).
