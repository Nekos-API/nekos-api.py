"""
Documentation: https://nekosapi.com/docs/libraries/python/
API documentation: https://nekosapi.com/docs/
"""
from uuid import UUID
from datetime import datetime

import typing
import time
import urllib.parse

import requests
import dateutil

from .pagination import PaginatedResult
from .ratelimiting import prevent_ratelimit
from .types import VerificationStatus
from .utils import to_camel_case
from .exceptions import UnspecifiedResourceError


def image_property(func: typing.Callable):
    """
    When a function has this decorator, it means that the function cannot be
    called without the image's data being loaded first. If the data is not
    loaded, the Image._load() method is called before the function execution.

    This wrapper also adds the @property decorator to the function.
    """

    def wrapper(*args, **kwargs):
        self = args[0]

        try:
            # Check that an ID has been set
            self.id
        except AttributeError:
            raise UnspecifiedResourceError()

        if not self._loaded:
            self._load()

        return func(*args, **kwargs)

    return wrapper


class Image:
    """
    The image's object representation class. You can use this class either to
    make queries to the API or to represent an image resource.
    """

    @property
    def id(self) -> UUID:
        """
        The image's resource ID.
        """
        try:
            return self._id

        except AttributeError:
            # The AttributeError is excepted to modify the error's explanation.
            raise AttributeError(
                "The object was not assigned to a resource, and therefore you cannot get it's ID."
            )

    @property
    def pk(self) -> UUID:
        """
        Another way of getting the ID of the image.
        """
        return self.id

    @property
    @image_property
    def title(self) -> typing.Optional[str]:
        """
        The image's title.
        """
        return self._data["data"]["attributes"]["title"]

    @property
    @image_property
    def url(self) -> typing.Optional[str]:
        """
        The image's file URL.
        """
        return self._data["data"]["attributes"]["file"]

    @property
    @image_property
    def colors(self) -> object:
        """
        An object with the image's colors.
        """

        class Colors:
            primary = property(
                lambda get: self._data["data"]["attributes"]["colors"]["primary"]
            )
            dominant = property(
                lambda get: self._data["data"]["attributes"]["colors"]["dominant"]
            )

        return Colors()

    @property
    @image_property
    def source(self) -> object:
        """
        The image's source url and name.
        """

        class Source:
            name = property(
                lambda get: self._data["data"]["attributes"]["source"]["name"]
            )
            url = property(
                lambda get: self._data["data"]["attributes"]["source"]["url"]
            )

        return Source()

    @property
    @image_property
    def dimens(self) -> object:
        """
        The image's dimensions.
        """

        class Dimens:
            height = property(
                lambda get: self._data["data"]["attributes"]["dimens"]["height"]
            )
            width = property(
                lambda get: self._data["data"]["attributes"]["dimens"]["width"]
            )
            aspect_ratio = property(
                lambda get: self._data["data"]["attributes"]["dimens"]["width"]
            )

        return Dimens()

    @property
    @image_property
    def verification_status(self) -> VerificationStatus:
        """
        The image's current verification status. For public images, this will
        always be `VerificationStatus.VERIFIED` because unverified images are
        hidden. For images uploaded by the logged in user, the status can be
        one of the four statuses available.
        """
        return VerificationStatus(
            self._data["data"]["attributes"]["verificationStatus"]
        )

    @property
    @image_property
    def timestamps(self) -> object:
        """
        The image's creation and last updated timestamps.
        """

        class Timestamps:
            created = property(
                lambda get: dateutil.parser.parse(
                    self._data["data"]["attributes"]["timestamps"]["created"]
                )
            )
            updated = property(
                lambda get: dateutil.parser.parse(
                    self._data["data"]["attributes"]["timestamps"]["updated"]
                )
            )

        return Timestamps()

    @property
    @image_property
    def is_original(self) -> bool:
        """
        Wether the image is original (`True`) or a fanart (`False`).
        """
        return self._data["data"]["attributes"]["isOriginal"]

    def __init__(self, *args, **kwargs) -> None:
        """
        Initializes the object with the provided data.
        """
        self._loaded: bool = False

        if "id" in kwargs:
            self._id = (
                UUID(kwargs["ID"])
                if not isinstance(kwargs["ID"], UUID)
                else kwargs["ID"]
            )

        if "data" in kwargs:
            self._load_from_resource(data=kwargs["data"])

    @prevent_ratelimit
    def get(id: typing.Union[UUID, str]) -> "Image":
        """
        Returns an image by it's ID.
        """
        r = requests.get(
            f"https://api.nekosapi.com/v2/images/{urllib.parse.quote(str(id))}",
            headers={"Accept": "application/vnd.api+json"},
        )
        r.raise_for_status()

        return Image(data=r.json())

    @prevent_ratelimit
    def random(**filters) -> "Image":
        """
        Returns a random image.

        You can pass the filters as arguments with a double underscore (`__`)
        separating the field name from the lookup method. For example,
        `age_rating__iexact`. To use the filter without the lookup method, just
        omit the `__lookup` part of the filter. For example, `age_rating`.
        """
        params = {}

        for key in filters.keys():
            query_name = (
                f"filter[{'.'.join([to_camel_case(i) for i in key.split('__', 1)])}]"
            )
            params[query_name] = filters[key]

        r = requests.get(
            f"https://api.nekosapi.com/v2/images/random",
            headers={"Accept": "application/vnd.api+json"},
            params=params,
        )
        r.raise_for_status()

        return Image(data=r.json())

    def search(
        sort: typing.Union[typing.List[str], str, type(None)] = None,
        included: typing.Union[typing.List[str], str, type(None)] = None,
        **filters,
    ) -> PaginatedResult:
        """
        Search for an image.

        You can pass the filters as arguments with a double underscore (`__`)
        separating the field name from the lookup method. For example,
        `age_rating__iexact`. To use the filter without the lookup method, just
        omit the `__lookup` part of the filter. For example, `age_rating`.

        You can also prefetch related resources like the artist or characters
        by specifying the `included` argument. `included="artist"` will
        prefetch the artist resource, so no request will be made when you
        access `image.artist`. To prefetch multiple related resources, you will
        need to use a list instead of a string. E.g.
        `included=["artist", "characters"]` will prefetch both artists and
        characters.

        To sort results, you can use the `sort` argument. `sort="createdAt"`
        will sort the results by the date the resource was created. Prepending
        a `-` character to the name will reverse the order and the results will
        be sorted descendingly. You can also use a list to sort by multiple
        properties. E.g. `sort=["-createdAt", "title"]` will sort items using
        `-createdAt` and sort the items with the same `createdAt` by the title
        in alphabetical order.
        """

        params = {}

        for key in filters.keys():
            query_name = (
                f"filter[{'.'.join([to_camel_case(i) for i in key.split('__', 1)])}]"
            )
            params[query_name] = filters[key]

        if isinstance(sort, str):
            params["sort"] = sort
        elif isinstance(sort, list):
            params["sort"] = ",".join(sort)

        if isinstance(included, str):
            params["included"] = included
        elif isinstance(included, list):
            params["included"] = ",".join(included)
        
        return PaginatedResult(
            url="https://api.nekosapi.com/v2/images",
            params=params
        )

    @prevent_ratelimit
    def _load(self):
        """
        Fetches the image's data from the API.
        """

        try:
            r = requests.get(
                f"https://api.nekosapi.com/v2/images/{urllib.parse.quote(str(self.id))}",
                headers={"Accept": "application/vnd.api+json"},
            )
            r.raise_for_status()

        except AttributeError:
            raise UnspecifiedResourceError()

        self._load_from_resource(r.json())

    def _load_from_resource(self, data: dict):
        """
        Loads all the image's properties to the object.
        """

        self._id = UUID(data["data"]["id"])
        self._data = data

        # Prevent from being refetched from the API.
        self._loaded = True
