"""Setup script for HaikuPorter
"""
import sys
import warnings
if sys.version_info[:2] != (3, 4):
	warnings.warn("Python 3.4 is required")

from setuptools import setup

from HaikuPorter.__version__ import __version__

setup(name='HaikuPorter',
	packages=["HaikuPorter"],
	version=__version__,
	description="Haiku package management",
	author="Haiku, Inc. See also AUTHORS.txt",
	setup_requires=['install_binaries'],
	install_binaries=['haikuporter'],
	license="MIT",
	requires=[
		  'python (>=3.4.0)',
		  ],
	classifiers=[
		  'Operating System :: Haiku',
		  'License :: OSI Approved :: MIT License',
		  'Programming Language :: Python',
		  'Programming Language :: Python :: 3.4',
		  ],
	)
