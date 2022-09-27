import setuptools
import marjapussi

with open("README.md", 'r') as f:
    long_description = f.read()

setuptools.setup(
    name="marjapussi",
    version=marjapussi.__version__,
    author=marjapussi.__author__,
    author_email="Samuel@LMpost.de",
    description="Python Implementation of MarjaPussi.",
    long_description=long_description,
    packages=["marjapussi"],
    python_requires='>=3.9',
)
