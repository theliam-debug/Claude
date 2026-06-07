"""
Setup file for derivatives_strategies v3.
"""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="derivatives_strategies",
    version="3.0.0",
    author="Derivatives Strategies Team",
    description="Institutional, Policy-Driven Options Overlay Toolkit",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(exclude=["tests", "examples"]),
    python_requires=">=3.11",
    install_requires=[
        # Standard library only - no external dependencies required
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "ruff>=0.6",
        ],
    },
    entry_points={
        "console_scripts": [
            "ds3=derivatives_strategies.engine.runner:run_cli",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Office/Business :: Financial :: Investment",
    ],
)
