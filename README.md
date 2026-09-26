# WASMixer

WASMixer consists of two main functions: the data obfuscator and the code obfuscator. The data obfuscator randomizes readable names and encrypts/decrypts memory areas at runtime. The code obfuscator manipulates instructions and control flow through techniques like alias disruption, control flow flattening, and Collatz-based opaque predicates to thwart human reverse engineering and static analysis.

## Getting Started

### Docker

1.   set environment

WASMixer should run well on a server with Ubuntu 22.04.
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
