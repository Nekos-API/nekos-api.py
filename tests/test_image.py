"""
Test the Image.get method.
"""
from uuid import UUID

from nekosapi import Image
from nekosapi.types import AgeRating


def test_get_image():
    img = Image.get("cf170732-21b3-4577-b58f-7b390b6912d7")
    assert isinstance(img.pk, UUID)


def test_random_image():
    img = Image.random()
    assert isinstance(img.pk, UUID)

def test_search_image():
    imgs = Image.search(age_rating__iexact='sfw')
    print("First")
    imgs[2:5]
    print("Second")
    imgs[2:5]
    print("Third")
    