class UnspecifiedResourceError(Exception):
    """
    Raised when an ID is required but the object hasn't got one.
    """

    def __init__(self):
        super().__init__(
            "The resource has no ID. Therefore, no resource can be fetched from the API."
        )
