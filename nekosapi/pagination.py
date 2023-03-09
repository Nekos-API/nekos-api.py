import typing

import requests

from .ratelimiting import prevent_ratelimit
from .exceptions import AlreadyLoadedException


class PaginatedResult:
    """
    This class automatically handles paginated results.
    """

    def __init__(
        self,
        url: str,
        params: dict = {},
        headers: dict = {"Accept": "application/vnd.api+json"},
    ) -> None:
        """
        Initializes the PaginatedResult object with the provided parameters.
        The object does not make any query until the objects are fetched.
        """

        # The loaded items variable is a dictionary because some indexes may be
        # omitted in the queries. For example, if the user fetches from index
        # 10 to 30, then all items up to 10 are omitted and all those after 30
        # too.
        self._loaded_items = {}

        self.url = url
        self.params = params
        self.headers = headers

    def __getitem__(self, key: typing.Union[slice, int]):
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
                # allows 50 items per page. TODO: Reduce query size by trying
                # to omit already loaded items.
                offsets = [
                    key.start + offset
                    for offset in range(
                        0, len(sliced_indexes) + len(sliced_indexes) % 50, 50
                    )
                ]

                for offset in offsets:
                    params = self.params
                    params.update({"page[limit]": 50, "page[offset]": offset})

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
                    self._loaded_items[offset + n] = TYPE_TO_CLASS[item["type"]](
                        data={"data": item, "included": r.json().get("included", None)}
                    )
                    n += 1
                
            return self._loaded_items[key]

    def _get_best_page(item: int):
        """
        This function returns the best limit-offset page that will allow to
        fetch a specific item while fetching other items for caching.

        Returns two values: `limit` and `offset`.
        """
        if self._loaded_items.get(item, None) is not None:
            raise AlreadyLoadedException()

        loaded_items = (list(self._loaded_items.keys()) + [item]).sort()
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

        if next_item - prev_item > 50:
            # The gap between the previous and the next items is greater than
            # 50 so all items cannot be loaded in a single request. The page is
            # shortened to reach a max of 50 items.

            while next_item - prev_item > 50:
                # This loop reduces the page's size to make it reach the max 50
                # allowed items per page. Both page start and page end are
                # reduced at the same speed (i.e. start + 1, end - 1 both occur
                # at the same time).

                # Reduce the next item only if it is not the item that needs to
                # be fetched. The same thing is done with the previous item.
                if next_item != item_index:
                    next_item -= 1

                if next_item - prev_item > 50:
                    if prev_item != item_index:
                        prev_item += 1

        # Return the limit and offset.
        return next_item - prev_item, prev_item
