# Tests for session-add-in-loop rule.


# ruleid: session-add-in-loop
def bad_for_loop(items, session):
    for item in items:
        obj = MyModel(value=item)
        session.add(obj)
    session.commit()


# ruleid: session-add-in-loop
def bad_while_loop(items, session):
    while items:
        item = items.pop()
        obj = MyModel(value=item)
        session.add(obj)
    session.commit()


# ok: begin_nested savepoint in for loop
def ok_for_nested(items, session):
    for item in items:
        with session.begin_nested():
            obj = MyModel(value=item)
            session.add(obj)
    session.commit()


# ok: begin_nested savepoint in while loop
def ok_while_nested(items, session):
    while items:
        item = items.pop()
        with session.begin_nested():
            obj = MyModel(value=item)
            session.add(obj)
    session.commit()


# ok: add outside loop
def ok_outside_loop(items, session):
    for item in items:
        process(item)
    obj = MyModel(value="final")
    session.add(obj)
    session.commit()


class MyModel:
    def __init__(self, value):
        self.value = value


def process(item):
    pass
