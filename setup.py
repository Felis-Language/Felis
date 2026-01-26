from setuptools import setup, find_packages

setup(
    name="felis-lang",
    version="1.0.0",
    description="A programming language that compiles to Scratch SB3",
    author="Felis Team",
    packages=find_packages(),
    package_data={
        "felis": ["stdlib/*.felis"]
    },
    entry_points={
        "console_scripts": [
            "felis=felis.cli:main",
        ],
    },
    install_requires=[
        # no external dependencies for now
    ],
    python_requires=">=3.8",
)
