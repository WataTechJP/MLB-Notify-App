from dataclasses import dataclass


@dataclass(frozen=True)
class PlayerInfo:
    id: int
    name_ja: str
    name_en: str
    position: str  # "batter" | "pitcher" | "two_way"
    team: str


JAPANESE_PLAYERS: list[PlayerInfo] = [
    PlayerInfo(id=660271, name_ja="大谷翔平", name_en="Shohei Ohtani", position="two_way", team="LAD"),
    PlayerInfo(id=807799, name_ja="吉田正尚", name_en="Masataka Yoshida", position="batter", team="BOS"),
    PlayerInfo(id=673548, name_ja="鈴木誠也", name_en="Seiya Suzuki", position="batter", team="CHC"),
    PlayerInfo(id=681936, name_ja="今永昇太", name_en="Shota Imanaga", position="pitcher", team="CHC"),
    PlayerInfo(id=579328, name_ja="菊池雄星", name_en="Yusei Kikuchi", position="pitcher", team="TOR"),
]

# player_id → PlayerInfo の辞書 (検索用)
PLAYER_MAP: dict[int, PlayerInfo] = {p.id: p for p in JAPANESE_PLAYERS}

# 野手 player_id セット (ホームラン検知対象)
BATTER_IDS: frozenset[int] = frozenset(
    p.id for p in JAPANESE_PLAYERS if p.position in ("batter", "two_way")
)

# 投手 player_id セット (奪三振検知対象)
PITCHER_IDS: frozenset[int] = frozenset(
    p.id for p in JAPANESE_PLAYERS if p.position in ("pitcher", "two_way")
)
