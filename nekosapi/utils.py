def to_camel_case(snake_str: str):
    """
    Converts a snake_case string to camelCase.
    """

    components = snake_str.split("_")
    return components[0] + "".join(x.title() for x in components[1:])


def to_dasherized(snake_str: str):
    """
    Converts a snake_case string to dasherized string.
    """
    return snake_str.replace("_", "-")

def to_snake_case_from_dasherized(dasherized: str):
    """
    Converts a dasherized string to a snake_case string.
    """
    return snake_str.replace("-", "_")
