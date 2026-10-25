from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="jetrauserapi",
    version="1.0.1",
    author="Ali VEX",
    author_email="lyrdaadhrpyk802@gmail.com",
    description="A Python library for interacting with Jetra Messenger (User Account)",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/lyrdaadhrpyk802-ux/JetraUserAPI",
    packages=find_packages(exclude=["examples", "examples.*"]),
    install_requires=[
        "websockets>=10.0",
        "pycryptodome>=3.15.0",
    ],
    python_requires=">=3.10",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Topic :: Communications :: Chat",
    ],
    keywords="jetra messenger api client telethon",
)
