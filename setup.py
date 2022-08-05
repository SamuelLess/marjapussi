import setuptools

with open("README.md", 'r') as f:
    long_description = f.read()

setuptools.setup(
    name="marjapussi",
    version="0.1",
    author="Samuel Leßmann",
    author_email="Samuel@LMpost.de",
    description="Python Implementation of MarjaPussi.",
    long_description=long_description,
    packages=["marjapussi"],
    python_requires='>=3.9',
)
