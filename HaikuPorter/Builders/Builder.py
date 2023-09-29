# Copyright 2015 Michael Lotz
# Copyright 2016 Jerome Duval
# Distributed under the terms of the MIT License.
from enum import Enum


class BuilderState(Enum):
    AVAILABLE = "Available"
    LOST = "Lost"
    NOT_AVAILABLE = "Not Available"
    RECONNECT = "Reconnecting"

