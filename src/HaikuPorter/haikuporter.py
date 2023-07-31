#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2013-2014 Oliver Tappe
# Distributed under the terms of the MIT License.
import logging

from HaikuPorter.Main import Main
from HaikuPorter.Options import parseOptions


def main():
    logger = logging.getLogger("buildLogger")
    logger.setLevel(logging.INFO)
    logger.addHandler(logging.StreamHandler())

    Main(*parseOptions())


if __name__ == "__main__":
    main()
