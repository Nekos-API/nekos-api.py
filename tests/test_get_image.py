"""
Test the Image.get method.
"""
from uuid import UUID

from nekosapi import Image


def test_get_image():
    img = Image.get("cf170732-21b3-4577-b58f-7b390b6912d7")
    assert isinstance(img.pk, UUID)
