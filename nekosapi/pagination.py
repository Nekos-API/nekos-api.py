import typing

import requests

from .ratelimiting import prevent_ratelimit
from .exceptions import AlreadyLoadedException


class PaginatedResult:
    """
    This class handles paginated results. Requests are not made to the API
    until resources are requested. For example:

    .. highlight:: python
    .. code-block:: python

        # No request was made
        images: PaginatedResult = Image.search(age_rating__iexact="sfw")

        # The first 50 items are fetched from the API
        images[0]

        # These items have been previously loaded so no request is made
        images[0]
        images[24]
        images[48]

        # A new request is made to fetch these objects. Since the request allows up
        # to 50 items per request, items from 50 to 100 will be loaded to prevent
        # future unnecessary requests.
        images[57:84]

        # Again, these images have already been loaded so no request is made
        images[90:95]

    **WARNINGS:**
    Do not use `len(PaginatedResult)`. This will be extremely slow since it
    will load every single resource in the result. This will cause your program
    to get stuck at that line for many minutes and even hours. Instead, use the
    `PaginatedResult.count()` method which uses the API response metadata to
    count the items without fetching them all. If no request was made, the
    first `page_size` items will be fetched and cached. If a request has
    already been made, then the total amount of items has already been loaded
    and this method will not have any delay (because of the API request).
    """

    page_size: int = 50

    def __init__(
        self,
        url: str,
        params: dict = {},
        headers: dict = {"Accept": "application/vnd.api+json"},
        page_size: int = 50
    ) -> None:
        """Initializes the PaginatedResult object with the provided parameters.
        The object does not make any query until the objects are fetched.

        Args:
            url (str): The base URL where the resources are located.
            params (dict, optional): Any aditional query parameters that the request must have. Defaults to {}.
            headers (_type_, optional): Any aditional headers that the reqiuest must have. Defaults to {"Accept": "application/vnd.api+json"}.
            page_size (int, optional): The size of the pages to fetch. Defaults to 50 (the max page size allowed by the API).
        """

        # The loaded items variable is a dictionary because some indexes may be
        # omitted in the queries. For example, if the user fetches from index
        # 10 to 30, then all items up to 10 are omitted and all those after 30
        # too. In other words, items are not necessarily fetched in order.
        self._loaded_items: dict = {}
        self._count: typing.Optional[int] = None

        self._iter_current = 0

        self.url = url
        self.params = params
        self.headers = headers

        self.page_size = page_size

    def __getitem__(
        self, key: typing.Union[slice, int]
    ) -> typing.Union[object, typing.List[object]]:
        """Returns the selected items from the page. I.e. `PaginatedResult[5:10]`
        and `PaginatedResult[4]`.

        Args:
            key (typing.Union[slice, int]): The index or slice of the objects to get.

        Returns:
            typing.Union[object, typing.List[object]]: The resource or a list of the resources fetched.
        """
        # Imported inside the function to avoid circular imports.
        from .constants import TYPE_TO_CLASS

        if isinstance(key, slice):
            # Since the API does not support steps in pagination, all items
            # omitted by the steps need to be queried.
            sliced_indexes = range(key.start, key.stop + 1, key.step if key.step else 1)

            needs_request = False

            for i in sliced_indexes:
                if i not in self._loaded_items:
                    needs_request = True
                    break

            if needs_request:
                # Multiple requests may be needed since the max page size
                # allows `page_size` items per page. TODO: Reduce query size by
                # trying to omit already loaded items.
                offsets = [
                    key.start + offset
                    for offset in range(
                        0,
                        len(sliced_indexes) + len(sliced_indexes) % self.page_size,
                        self.page_size,
                    )
                ]

                for offset in offsets:
                    params = self.params
                    params.update({"page[limit]": self.page_size, "page[offset]": offset})

                    prevent_ratelimit()

                    r = requests.get(self.url, params=params, headers=self.headers)
                    r.raise_for_status()

                    n = 0
                    for item in r.json()["data"]:
                        self._loaded_items[offset + n] = TYPE_TO_CLASS[item["type"]](
                            data={
                                "data": item,
                                "included": r.json().get("included", None),
                            }
                        )
                        n += 1

                    self._count = r.json()["meta"]["pagination"]["count"]

            # Returns a list with all the items requested
            return [self._loaded_items[i] for i in sliced_indexes]

        else:
            # If the key is not a slice, then it is an integer
            item = self._loaded_items.get(key, None)

            if item is None:
                # The item is not loaded so it is fetched from the API together
                # with other extra items that will be cached for later use (in
                # case they are required).
                limit, offset = self._get_best_page(key)

                params = self.params
                params.update({"page[limit]": limit, "page[offset]": offset})

                prevent_ratelimit()

                r = requests.get(self.url, params=params, headers=self.headers)
                r.raise_for_status()

                n = 0
                for item in r.json()["data"]:
                    # Load each item as a Resource subclass object depending on
                    # the resource type.
                    self._loaded_items[offset + n] = TYPE_TO_CLASS[item["type"]](
                        data={"data": item, "included": r.json().get("included", None)}
                    )
                    n += 1

                self._count = r.json()["meta"]["pagination"]["count"]

            return self._loaded_items[key]

    def __iter__(self):
        """
        Initializes the iteration.
        """
        self._iter_current = 0
        return self

    def __next__(self):
        """
        Returns the next item when iterating.
        """
        # Imported inside the function to avoid circular imports.
        from .constants import TYPE_TO_CLASS

        item = self._loaded_items.get(self._iter_current, None)

        if item is None:
            # This item has not been loaded yet, so a request is made to get it
            # from the API.
            limit, offset = self._get_best_page(self._iter_current)

            params = self.params
            params.update({"page[limit]": limit, "page[offset]": offset})

            prevent_ratelimit()

            r = requests.get(self.url, params=params, headers=self.headers)
            r.raise_for_status()

            n = 0
            for item in r.json()["data"]:
                # Load each item as a Resource subclass object depending on
                # the resource type.
                self._loaded_items[offset + n] = TYPE_TO_CLASS[item["type"]](
                    data={"data": item, "included": r.json().get("included", None)}
                )
                n += 1

            # Cache the total amount of items.
            self._count = r.json()["meta"]["pagination"]["count"]

            item = self._loaded_items[self._iter_current]

        self._iter_current += 1

        return item

    def _get_best_page(self, item: int) -> typing.Tuple[int]:
        """This function returns the best limit-offset page that will allow to fetch a specific item while fetching other items for caching.

        Args:
            item (int): The index of the item that will be fetched. 

        Raises:
            AlreadyLoadedException: The resource has already been loaded (and it doesn't need refetching).

        Returns:
            typing.Tuple[int]: A tuple containing two items, the limit and the offset of the page.
        """
        if self._loaded_items.get(item, None) is not None:
            raise AlreadyLoadedException()

        loaded_items = list(self._loaded_items.keys()) + [item]
        loaded_items.sort()
        item_index = loaded_items.index(item)

        # If the item's index is 0 or the last of the loaded items, then use
        # the item as the start or the end of the page depending on wether it
        # is the first or last item.
        prev_item = loaded_items[item_index - 1] if item_index != 0 else item_index
        next_item = (
            loaded_items[item_index + 1]
            if item_index != len(loaded_items) - 1
            else item_index
        )

        if next_item - prev_item > self.page_size:
            # The gap between the previous and the next items is greater than
            # `page_size` so all items cannot be loaded in a single request.
            # The page is shortened to reach a max of `page_size` items.

            while next_item - prev_item > self.page_size:
                # This loop reduces the page's size to make it reach the max
                # `page_size` allowed items per page. Both page start and page
                # end are reduced at the same speed (i.e. start + 1, end - 1
                # both occur at the same time).

                # Reduce the next item only if it is not the item that needs to
                # be fetched. The same thing is done with the previous item.
                if next_item != item_index:
                    next_item -= 1

                if next_item - prev_item > self.page_size:
                    if prev_item != item_index:
                        prev_item += 1

        elif next_item - prev_item < self.page_size:
            # The gap between the previous and the next items is lower than
            # `page_size` so the limit and offset are modified to load as many
            # items as possible.

            while next_item - prev_item < self.page_size:
                # This loop reduces the page's size to make it reach the max
                # `page_size` allowed items per page. Both page start and page
                # end are reduced at the same speed (i.e. start + 1, end - 1
                # both occur at the same time).

                # This time no checks for equality are done (as in the previous
                # loop) because since the amount of items is expanded the
                # required item to fetch will never be left out.
                next_item += 1

                if next_item - prev_item < self.page_size:
                    if prev_item > 0:
                        prev_item -= 1

        # Finally, modify the items fetched to reduce the amount of already
        # loaded items in the response.
        while self._loaded_items.get(prev_item, None) is not None:
            prev_item += 1
            next_item += 1

        while self._loaded_items.get(next_item, None) is not None:
            if prev_item != 0:
                prev_item -= 1
            next_item -= 1

        # Return the limit and offset.
        return next_item - prev_item, prev_item

    @property
    def count(self) -> int:
        """
        Returns the total amount of resources.
        """
        # Imported inside the function to avoid circular imports.
        from .constants import TYPE_TO_CLASS

        if self._count is None:
            first_loaded_item = (
                list(self._loaded_items.keys()).sort()[0]
                if len(self._loaded_items.keys()) != 0
                else None
            )
            offset = None

            if first_loaded_item is None or first_loaded_item != 0:
                offset = 0
            else:
                # Since the first item was loaded (index: 0) we need to check
                # what is the first item that has not been loaded yet.
                i = 0
                for item_index in self._loaded_items.keys():
                    if item_index != i:
                        offset = item_index
                        break
                    i += 1

            params = self.params
            params.update({"page[limit]": self.page_size, "page[offset]": offset})

            prevent_ratelimit()

            r = requests.get(self.url, params=params, headers=self.headers)
            r.raise_for_status()

            n = 0
            for item in r.json()["data"]:
                self._loaded_items[offset + n] = TYPE_TO_CLASS[item["type"]](
                    data={"data": item, "included": r.json().get("included", None)}
                )
                n += 1

            self._count = r.json()["meta"]["pagination"]["count"]

        return self._count
