#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Copyright 2013-2014 Oliver Tappe
# Distributed under the terms of the MIT License.
try:
    from HaikuPorter.Main import Main
    from HaikuPorter.Options import parseOptions
except ImportError:
    from .src.HaikuPorter.Main import Main
    from .src.HaikuPorter.Options import parseOptions
import logging

logger = logging.getLogger("buildLogger")
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())

Main(*parseOptions())
