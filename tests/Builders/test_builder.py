# Copyright 2023 @jurgenwigg
# Distributed under the terms of the MIT License.
"""Unit tests for Builder.py module"""
from HaikuPorter.Builders.Builder import BuilderState
from pytest import mark


def test_number_of_possible_states():
    """Tests number of possible states.

    We assume that only 4 possible states are possible.
    """
    expected_value = 4
    actual_value = len(
        [item for item in BuilderState.__dict__.keys() if not item.startswith("__")]
    )
    assert expected_value == actual_value


@mark.parametrize(
    "state, expected_result",
    [
        ["AVAILABLE", "Available"],
        ["LOST", "Lost"],
        ["NOT_AVAILABLE", "Not Available"],
        ["RECONNECT", "Reconnecting"],
    ],
)
def test_is_state_present(state, expected_result):
    """Tests if given state returns expected state string."""
    assert BuilderState.__dict__[state] == expected_result
