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
    imgs.page_size = 25
    
    i = 0
    while i in range(50):
        image = next(imgs)
        assert image.age_rating == AgeRating.SAFE_FOR_WORK
        i += 1

def test_uploader():
    image: Image = Image.random()
    uploader = image.uploader
