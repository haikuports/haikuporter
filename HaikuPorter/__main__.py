# -*- coding: utf-8 -*-
#
# Copyright 2013-2014 Oliver Tappe
# Distributed under the terms of the MIT License.
import logging

from .Main import Main
from .Options import parseOptions


def main():
	logger = logging.getLogger("buildLogger")
	logger.setLevel(logging.INFO)
	logger.addHandler(logging.StreamHandler())

	Main(*parseOptions())


if __name__ == "__main__":
	main()
