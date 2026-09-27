from setuptools import setup, find_packages

setup(
    name="WASMixer",
    version="0.1.0",
    description="A tool for obfuscating WebAssembly binaries.",
    author="security-pride",
    packages=find_packages(where="."),
    package_dir={"WASMixer": "WASMixer"},
    install_requires=[
        "setuptools==68.0.0",
        "sphinx-tabs==3.4.1",
        "numpy>=1.25.2"
    ],
    python_requires='>=3.9',
    include_package_data=True,
    entry_points={},
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: Apache Software License",
        "Operating System :: OS Independent",
    ],
)
