from setuptools import setup, find_packages

with open("README.md", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="routewise",
    version="0.1.2",
    description="Client SDK for the routewise cost-aware LLM router",
    long_description=long_description,
    long_description_content_type="text/markdown",
    packages=find_packages(),
    install_requires=["requests"],
    python_requires=">=3.8",
)