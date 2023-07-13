# -*- coding: utf-8 -*-
#
# Copyright 2015 Michael Lotz
# Copyright 2016 Jerome Duval
# Distributed under the terms of the MIT License.


class _BuilderState(object):
    AVAILABLE = "Available"
    LOST = "Lost"
    NOT_AVAILABLE = "Not Available"
    RECONNECT = "Reconnecting"
