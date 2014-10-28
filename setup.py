"""Setup script for HaikuPorter
"""
import sys
import warnings
if sys.version_info[:2] != (2, 7):
    warnings.warn("Python 2.7 is required")

from setuptools import setup

from HaikuPorter.__version__ import __version__

setup(name='HaikuPorter',
    packages=["HaikuPorter"],
    version=__version__,
    description="Haiku package management",
    author="Haiku, Inc. See also AUTHORS.txt",
    license="MIT",
    requires=[
          'python (>=2.7.0)',
          ],
    classifiers=[
          'Operating System :: Haiku',
          'License :: OSI Approved :: MIT License',
          'Programming Language :: Python',
          'Programming Language :: Python :: 2.7',
          ],
    )
