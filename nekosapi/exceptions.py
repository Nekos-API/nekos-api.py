import typing


class UnspecifiedResourceError(Exception):
    """
    Raised when an ID is required but the object hasn't got one.
    """

    def __init__(self):
        super().__init__(
            "The resource has no ID. Therefore, no resource can be fetched from the API."
        )


class AlreadyLoadedException(Exception):
    """
    Raised when a resource has already been loaded and there was an
    unauthorized attempt to refetch it.
    """

    def __init__(self, resource_id: typing.Optional[str] = None):
        super().__init__(
            "This resource has already been loaded. There is no need to fetch it again."
            + (f" Resource ID: {resource_id}" if resource_id else "")
        )
