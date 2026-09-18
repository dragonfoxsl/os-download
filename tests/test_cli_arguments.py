import argparse

import pytest

from os_download.cli.common import positive_int


def test_positive_int_accepts_positive_values():
    assert positive_int("7") == 7


@pytest.mark.parametrize("value", ["0", "-1", "nope"])
def test_positive_int_rejects_invalid_values(value: str):
    with pytest.raises(argparse.ArgumentTypeError):
        positive_int(value)
