from uuid import UUID
from datetime import datetime

import typing
import time
import urllib.parse

import requests
import dateutil

from .pagination import PaginatedResult
from .ratelimiting import prevent_ratelimit
from .types import VerificationStatus, AgeRating, Sub, ListWithRefs
from .utils import to_camel_case, to_dasherized, to_snake_case_from_dasherized
from .exceptions import UnspecifiedResourceError


def resource_property(func: typing.Callable):
    """When a function has this decorator, it means that the function cannot be
    called without the resource's data being loaded first. If the data is not
    loaded, the Resource._load() method is called before the function
    execution.

    Args:
        func (typing.Callable): The function to wrap.
    """

    def wrapper(*args, **kwargs):
        obj = args[0]

        try:
            # Check that an ID has been set
            obj.id
        except AttributeError:
            raise UnspecifiedResourceError()

        if not obj._loaded:
            obj._load()

        return func(*args, **kwargs)

    return wrapper


def resource_relationship(func: typing.Callable, related_resource_name: typing.Optional[str] = None):
    """This decorator loads the relationship data before it is returned by the
    image. All resource property functions are decorated by this wrapper.

    Args:
        func (typing.Callable): The function to wrap.
    """

    def wrapper(*args, **kwargs):
        # Imported inside the function to prevent circular imports.
        from .constants import TYPE_TO_CLASS

        obj = args[0]

        try:
            # Check that an ID has been set
            obj.id
        except AttributeError:
            raise UnspecifiedResourceError()

        # API resource names are dasherized. E.g. image-source-result,
        # api-details.
        related_resource_name = to_dasherized(func.__name__)
        related_resource_url = None

        if related_resource_name not in obj._loaded_relationships:
            relationship_data = obj._data["data"]["relationships"].get(
                related_resource_name, None
            )

            if obj._loaded:
                # The relationship data will only be available if the resource
                # has been already loaded. TODO: Optimize requests using
                # included resources previously loaded.
                if relationship_data is None:
                    raise Exception(
                        f"There is no relationship named `{related_resource_name}`."
                    )
                else:
                    # There is data for the relationship, so a check is made to
                    # use included resources if there are any.
                    if obj._data.get("included", None) is not None:
                        included_resources = obj._data["included"]
                        related_resources = (
                            relationship_data["data"]
                            if isinstance(relationship_data["data"], list)
                            else [relationship_data["data"]]
                        )

                        resources = []

                        for included_resource in included_resources:
                            for related_resource in related_resources:
                                if (
                                    included_resource["type"]
                                    == related_resource["type"]
                                    and included_resource["id"]
                                    == related_resource["id"]
                                ):
                                    # The resource is the same so it is added
                                    # to the `preloaded_resources` list.
                                    resources.append(included_resource)

                        resources += [
                            resource
                            for resource in related_resources
                            if resource["id"]
                            not in [item["id"] for item in included_resources]
                        ]

                        if isinstance(relationship_data["data"], list):
                            # There are many related resources. Some may have
                            # not been included.
                            obj._loaded_relationships[related_resource_name] = [
                                TYPE_TO_CLASS[item["type"]](
                                    data={"data": item, "included": included_resources}
                                )
                                if item.get("attributes", None) is not None
                                else TYPE_TO_CLASS[item["type"]](id=item["id"])
                                for item in resources
                            ]
                            return func(*args, **kwargs)

                        elif len(resources) > 0:
                            # The relationship is a one-to-one or one-to-many
                            # relationship so only one resource can be
                            # included.
                            obj._loaded_relationships[
                                related_resource_name
                            ] = TYPE_TO_CLASS[resources[0]["type"]](
                                data={
                                    "data": resources[0],
                                    "included": included_resources,
                                }
                            )
                            return func(*args, **kwargs)

                links = relationship_data.get("links", None)

                if "data" in relationship_data:
                    if (
                        relationship_data["data"] is None
                        or relationship_data["data"] == []
                    ):
                        # There is no resource for this relationship, so no
                        # request is made to the API.
                        self._loaded_relationships[
                            related_resource_name
                        ] = relationship_data["data"]
                        return func(*args, **kwargs)

                # If the resource link is provided, then use that URL to fetch the
                # related resources. Otherwise, generate the URL with the resource's
                # data.
                if links is not None:
                    related_resource_url = links["related"]
                else:
                    related_resource_url = f"https://api.nekosapi.com/v2/{obj.resource_name_plural}/{obj.id}/{related_resource_name}"

            else:
                related_resource_url = f"https://api.nekosapi.com/v2/{obj.resource_name_plural}/{obj.id}/{related_resource_name}"

            prevent_ratelimit()

            r = requests.get(related_resource_url)
            r.raise_for_status()

            data = r.json()

            raw_resources = []

            if isinstance(data["data"], dict):
                # There is only one resource.
                raw_resources = [data["data"]]

            elif isinstance(data["data"], list):
                raw_resources = data["data"]

            elif data["data"] is None:
                # There is no resource, so no extra serialization needs to be
                # made. `None` is returned directly.
                self._loaded_relationships[related_resource_name] = None
                return func(*args, **kwargs)

            initialized_resources = []

            for item in raw_resources:
                initialized_resources.append(
                    TYPE_TO_CLASS[item["type"]](
                        data={"data": item, "included": data.get("included", None)}
                    )
                )

            if isinstance(data["data"], dict):
                obj._loaded_relationships[
                    related_resource_name
                ] = initialized_resources[0]
            else:
                obj._loaded_relationships[related_resource_name] = initialized_resources

        return func(*args, **kwargs)

    return wrapper


class Resource:
    """The base class for all resource classes (Image, User, etc.). It is useful
    for type checking.

    Raises:
        UnspecifiedResourceError: The resource's ID is not defined.
    """

    resource_name: str
    resource_name_plural: str

    def __init__(self, *args, **kwargs) -> None:
        """
        Initializes the object with the provided data.
        """
        self._loaded: bool = False
        self._loaded_relationships = {}

        self.headers = {"Accept": "application/vnd.api+json"}
        self.params = {}

        if "id" in kwargs:
            self._id = (
                UUID(kwargs["id"])
                if not isinstance(kwargs["id"], UUID)
                else kwargs["id"]
            )

        if "data" in kwargs:
            self._load_from_resource(data=kwargs["data"])

    @property
    def id(self) -> typing.Union[UUID, str]:
        """
        The resource's ID.
        """
        try:
            return self._id

        except AttributeError:
            # The AttributeError is excepted to modify the error's explanation.
            raise UnspecifiedResourceError()

    @property
    def pk(self) -> typing.Union[UUID, str]:
        """
        Another way of getting the resource's ID.
        """
        return self.id

    @prevent_ratelimit
    def _load(self):
        """
        Fetches the resource's data from the API.
        """

        try:
            r = requests.get(
                f"https://api.nekosapi.com/v2/{self.resource_name_plural}/{urllib.parse.quote(str(self.id))}",
                headers=self.headers,
                params=self.params,
            )
            r.raise_for_status()

        except AttributeError:
            raise UnspecifiedResourceError()

        self._load_from_resource(r.json())

    def _load_from_resource(self, data: dict):
        """Loads all the resource's properties to the object.

        Args:
            data (dict): The resource's data. Must have a `data` key in the top level.
        """

        self._id = UUID(data["data"]["id"])
        self._data = data

        # Prevent from being refetched from the API.
        self._loaded = True

        return True

    def is_loaded(self):
        """
        Returns wether the resource has been loaded or not.
        """
        return self._loaded

    def is_relationship_loaded(self, relationship_name: str):
        """
        Returns wether a specific relationship has been loaded or not.
        """
        return to_dasherized(relationship_name) in self._loaded_relationships

    def include(self, *relationships: typing.Tuple[str]) -> "Resource":
        """If a resource has not been loaded, using this method will add
        relationships to the `included` parameter to reduce the amount of
        requests needed to fetch the resource's data and it's relationships.

        Returns:
            Resource: The instance of the resource. This is useful for chaining
                      methods.
        """
        return self

    @prevent_ratelimit
    def fetch_relationships(
        self, *relationships: typing.Tuple[str], ignore_loaded: bool = False
    ):
        """
        Makes a request to the API's resource endpoint with the `include`
        parameter to fetch many relationships at once.
        """
        if len(relationships) == 0:
            return

        # Imported here to avoid a circular import error.
        from .constants import TYPE_TO_CLASS

        params = self.params.copy()
        params.update(
            {
                "include": ",".join(
                    [
                        to_dasherized(relationship)
                        for relationship in relationships
                        if ignore_loaded
                        or not self.is_relationship_loaded(relationship)
                    ]
                )
            }
        )

        r = requests.get(
            f"https://api.nekosapi.com/v2/{self.resource_name_plural}/{urllib.parse.quote(str(self.id))}",
            headers=self.headers,
            params=params,
        )
        r.raise_for_status()

        data = r.json()

        for relationship in relationships:
            if self.is_relationship_loaded(relationship) and ignore_loaded:
                continue

            refs = data["data"]["relationships"][to_camel_case(relationship)]["data"]

            if isinstance(refs, list):
                self._loaded_relationships[relationship] = []

                ids = [ref["id"] for ref in refs]

                for resource in data["included"]:
                    if (
                        resource["id"] in ids
                        and resource["type"] == refs[ids.index(resource["id"])]["type"]
                    ):
                        self._loaded_relationships[relationship].append(
                            TYPE_TO_CLASS[resource["type"]](
                                data={
                                    "data": resource,
                                    "included": data.get("included", None),
                                }
                            )
                        )

            elif isinstance(refs, dict):
                for resource in data["included"]:
                    if (
                        resource["id"] == refs["id"]
                        and resource["type"] == refs["type"]
                    ):
                        self._loaded_relationships[relationship] = TYPE_TO_CLASS[
                            resource["type"]
                        ](
                            data={
                                "data": resource,
                                "included": data.get("included", None),
                            }
                        )
                        break

            else:
                # There is no resource, so no extra serialization needs to be
                # made. `None` is returned directly.
                self._loaded_relationships[relationship] = None

        return self

    @prevent_ratelimit
    def get(id: typing.Union[UUID, str]) -> "Resource":
        """
        Returns a resource by it's ID.
        """
        r = requests.get(
            f"https://api.nekosapi.com/v2/{self.resource_name_plural}/{urllib.parse.quote(str(id))}",
            headers={"Accept": "application/vnd.api+json"},
        )
        r.raise_for_status()

        return self.__class__(data=r.json())


class Image(Resource):
    """
    The image's object representation class. You can use this class either to
    make queries to the API or to represent an image resource.
    """

    resource_name = "image"
    resource_name_plural = "images"

    @property
    @resource_property
    def title(self) -> typing.Optional[str]:
        """
        The image's title.
        """
        return self._data["data"]["attributes"]["title"]

    @property
    @resource_property
    def url(self) -> typing.Optional[str]:
        """
        The image's file URL.
        """
        return self._data["data"]["attributes"]["file"]

    @property
    @resource_property
    def colors(self) -> object:
        """
        An object with the image's colors.
        """

        class Colors:
            dominant = property(
                lambda get: self._data["data"]["attributes"]["colors"]["dominant"]
            )
            palette = property(
                lambda get: self._data["data"]["attributes"]["colors"]["palette"]
            )

        return Colors()

    @property
    @resource_property
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
    @resource_property
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
    @resource_property
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
    @resource_property
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
    @resource_property
    def is_original(self) -> bool:
        """
        Wether the image is original (`True`) or a fanart (`False`).
        """
        return self._data["data"]["attributes"]["isOriginal"]

    @property
    @resource_property
    def age_rating(self) -> typing.Optional[AgeRating]:
        """
        Wether the image is original (`True`) or a fanart (`False`).
        """
        raw_value = self._data["data"]["attributes"]["ageRating"]
        return AgeRating(raw_value) if raw_value is not None else None

    @property
    @resource_relationship
    def uploader(self) -> "User":
        """
        The user who uploaded the image to the API.
        """
        return self._loaded_relationships["uploader"]

    @property
    @resource_relationship
    def categories(self) -> typing.List["Category"]:
        """
        The categories the image belongs to.
        """
        return self._loaded_relationships["categories"]

    @prevent_ratelimit
    def random(
        shared_resource_token: typing.Optional[str] = None, **filters
    ) -> "Image":
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

        if shared_resource_token is not None:
            params["token"] = shared_resource_token

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

        # No rate limiting checks are done because requests are not made until
        # the resources are required.
        return PaginatedResult(url="https://api.nekosapi.com/v2/images", params=params)

    @prevent_ratelimit
    def like(self):
        """
        Like an image.
        """
        r = requests.patch(
            f"https://api.nekosapi.com/v2/{self.id}/"
        )


class User(Resource):
    """
    The representation of an API user. You can use this class either to make
    queries to the API or to represent an image resource.
    """

    resource_name = "user"
    resource_name_plural = "users"

    @property
    @resource_property
    def username(self) -> str:
        """
        The username of the user.
        """
        return self._data["data"]["attributes"]["username"]

    @property
    @resource_property
    def nickname(self) -> typing.Optional[str]:
        """
        The nickname of the user.
        """
        return self._data["data"]["attributes"]["nickname"]

    @property
    @resource_property
    def name(self) -> str:
        """
        The name of the user.
        """

        class Name:
            first = property(
                lambda get: self._data["data"]["attributes"]["name"]["first"]
                if "name" in self._data["data"]["attributes"]
                else None
            )
            last = property(
                lambda get: self._data["data"]["attributes"]["name"]["last"]
                if "name" in self._data["data"]["attributes"]
                else None
            )

        return Name()

    @property
    @resource_property
    def avatar(self) -> str:
        """
        The avatar URL of the user.
        """
        return self._data["data"]["attributes"]["avatarImage"]

    @property
    @resource_property
    def biography(self) -> str:
        """
        The biography of the user.
        """
        return self._data["data"]["attributes"]["biography"]

    @property
    @resource_property
    def email(self) -> typing.Optional[str]:
        """
        The email of the user.
        """
        return self._data["data"]["attributes"]["email"]

    @property
    @resource_property
    def secret_key(self) -> typing.Optional[str]:
        """
        The secret key of the user.
        """
        return self._data["data"]["attributes"]["secretKey"]

    @property
    @resource_property
    def permissions(self) -> object:
        """
        The permissions of the user.
        """

        class Permissions:
            is_active = property(
                lambda get: self._data["data"]["attributes"]["permissions"]["isActive"]
            )
            is_staff = property(
                lambda get: self._data["data"]["attributes"]["permissions"]["isStaff"]
            )
            is_superuser = property(
                lambda get: self._data["data"]["attributes"]["permissions"][
                    "isSuperuser"
                ]
            )

        return Permissions()

    @property
    @resource_property
    def timestamps(self) -> object:
        """
        The timestamps of the user.
        """

        class Timestamps:
            joined = property(lambda get: self._data["data"]["attributes"]["joined"])

        return Timestamps()

    @property
    @resource_relationship
    def followers(self) -> list:
        """
        The followers of the user.
        """
        return self._loaded_relationships["followers"]

    @property
    @resource_relationship
    def following(self) -> list:
        """Returns a list of users that the usser is following.

        Returns:
            list: A list of users.
        """
        return self._loaded_relationships["following"]

    @property
    @resource_relationship
    def liked_images(self) -> list:
        """
        The liked images of the user.
        """
        return self._loaded_relationships["likedImages"]

    @property
    @resource_relationship
    def saved_images(self) -> list:
        """
        The saved images of the user.
        """
        return self._loaded_relationships["savedImages"]

    @property
    @resource_relationship
    def followed_categories(self) -> list:
        """
        The followed categories of the user.
        """
        return self._loaded_relationships["followedCategories"]

    def __str__(self):
        if self.is_loaded():
            return self.username
        else:
            return self.id


class Category(Resource):
    """
    The representation of a category.
    """

    resource_name = "category"
    resource_name_plural = "categories"

    @property
    @resource_property
    def name(self) -> str:
        """
        The name of the category.
        """
        return self._data["data"]["attributes"]["name"]

    @property
    @resource_property
    def description(self) -> str:
        """
        The description of the category.
        """
        return self._data["data"]["attributes"]["description"]

    @property
    @resource_property
    def sub(self) -> Sub:
        """
        The sub of the category.
        """
        return Sub(self._data["data"]["attributes"]["sub"])

    @property
    @resource_property
    def is_nsfw(self) -> bool:
        """
        Whether the category's name or description is NSFW. Usually this also
        means that the images/GIFs being categorized are also NSFW.
        """
        return self._data["data"]["attributes"]["isNsfw"]

    @property
    @resource_property
    def timestamps(self) -> object:
        """
        The timestamps of the category.
        """
        class Timestamps:
            created = property(lambda get: self._data["data"]["attributes"]["timestamps"]["created"])
            updated = property(lambda get: self._data["data"]["attributes"]["timestamps"]["updated"])

        return Timestamps()

    @property
    @resource_relationship
    def images(self) -> list:
        """
        The images of the category.
        """
        return self._loaded_relationships["images"]

    @property
    @resource_relationship
    def followers(self) -> list:
        """
        The followers of the category.
        """
        return self._loaded_relationships["followers"]
