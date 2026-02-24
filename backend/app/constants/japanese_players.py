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
    PlayerInfo(id=684007, name_ja="今永昇太", name_en="Shota Imanaga", position="pitcher", team="CHC"),
    PlayerInfo(id=579328, name_ja="菊池雄星", name_en="Yusei Kikuchi", position="pitcher", team="LAA"),
    PlayerInfo(id=506433, name_ja="ダルビッシュ有", name_en="Yu Darvish", position="pitcher", team="SD"),
    PlayerInfo(id=673540, name_ja="千賀滉大", name_en="Kodai Senga", position="pitcher", team="NYM"),
    PlayerInfo(id=808967, name_ja="山本由伸", name_en="Yoshinobu Yamamoto", position="pitcher", team="LAD"),
    PlayerInfo(id=808963, name_ja="佐々木朗希", name_en="Roki Sasaki", position="pitcher", team="LAD"),
    PlayerInfo(id=673513, name_ja="松井裕樹", name_en="Yuki Matsui", position="pitcher", team="SD"),
    PlayerInfo(id=829272, name_ja="小笠原慎之介", name_en="Shinnosuke Ogasawara", position="pitcher", team="WSH"),
    PlayerInfo(id=608372, name_ja="菅野智之", name_en="Tomoyuki Sugano", position="pitcher", team="BAL"),
    PlayerInfo(id=808959, name_ja="村上宗隆", name_en="Munetaka Murakami", position="batter", team="CWS"),
    PlayerInfo(id=672960, name_ja="岡本和真", name_en="Kazuma Okamoto", position="batter", team="TOR"),
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
