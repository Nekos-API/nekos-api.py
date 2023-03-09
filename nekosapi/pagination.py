import typing

import requests


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
        if isinstance(key, slice):
            # Since the API does not support steps in pagination, all items
            # omitted by the steps need to be queried.

            sliced_indexes = range(key.start, key.stop, key.step)

            needs_request = False

            for i in sliced_indexes:
                if i not in self._loaded_items:
                    needs_request = True
                    break

            if needs_request:
                # Multiple requests may be needed since the max page size
                # allows 50 items per page. TODO: Reduce query size by trying
                # to omit already loaded items.
                starts = [key.start + start for start in range(0, len(sliced_indexes) + len(sliced_indexes) % 50, 50)]

                for start in starts:
                    params = self.params
                    params.update({
                        "page[limit]": 50,
                        "page[offset]": start
                    })
            
            else:
                return [self._loaded_items[i] for i in sliced_indexes]


