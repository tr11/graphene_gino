import gino.declarative


def get_query(model, context):
    return model.query


def is_mapped_class(cls):
    try:
        return issubclass(cls, gino.declarative.Model)
    except Exception:
        return False


def is_mapped_instance(cls):
    try:
        return isinstance(cls, gino.declarative.Model)
    except Exception:
        return False


def to_type_name(name):
    """Convert the given name to a GraphQL type name."""
    return "".join(part[:1].upper() + part[1:] for part in name.split("_"))
