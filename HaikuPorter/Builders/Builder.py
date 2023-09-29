# Copyright 2015 Michael Lotz
# Copyright 2016 Jerome Duval
# Distributed under the terms of the MIT License.

class BuilderState:
	"""Provides mapping of builder state to string."""
	AVAILABLE = 'Available'
	LOST = 'Lost'
	NOT_AVAILABLE = 'Not Available'
	RECONNECT = 'Reconnecting'
