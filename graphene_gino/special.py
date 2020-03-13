def relationship(*args, **kwargs):
    return RelationshipProperty(*args, **kwargs)


class RelationshipProperty:
    def __init__(self, other, join: str, one: bool = False):
        self.other = other
        self.join = join
        self.one = one
