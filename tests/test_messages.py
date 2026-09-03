"""Tests for the SDK Message type."""

from tokenopt_optimizer import Message


def test_from_dict_defaults_role_and_content():
    m = Message.from_mapping({})
    assert m.role == "user"
    assert m.content == ""


def test_from_dict_with_name():
    m = Message.from_mapping({"role": "system", "content": "be brief", "name": "tutor"})
    assert m.role == "system"
    assert m.content == "be brief"
    assert m.name == "tutor"


def test_from_mapping_object_with_missing_attrs():
    class Obj:
        pass

    m = Message.from_mapping(Obj())
    assert m.role == "user"
    assert m.content == ""
    assert m.name is None


def test_from_mapping_object_with_attrs():
    class Obj:
        role = "assistant"
        content = "hello"
        name = "bot"

    m = Message.from_mapping(Obj())
    assert (m.role, m.content, m.name) == ("assistant", "hello", "bot")


def test_message_is_equal_dataclass():
    assert Message(role="user", content="x") == Message(role="user", content="x")
    assert Message(role="user", content="x") != Message(role="user", content="y")
