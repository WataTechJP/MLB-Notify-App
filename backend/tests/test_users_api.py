from app.api.v1.users import _iter_supported_event_types


def test_iter_supported_event_types_supports_legacy_player_id():
    assert _iter_supported_event_types(681936) == ("strikeout",)
