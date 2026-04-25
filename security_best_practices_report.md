# Security Best Practices Report

## Executive Summary

このプロジェクトは、通知送信の基本経路自体は動作しているが、API の認証境界が弱い。
特に `push_token` をそのまま公開識別子兼認証子として URL パスで扱っている点と、本番で有効化可能なテスト通知 API が無認証で公開される点は優先度が高い。

今回の修正で、Expo Push の `DeviceNotRegistered` を受けたトークンは自動で `is_active=false` に落とし、通知ログやクライアントエラーログでのトークン露出も一部削減した。

## High Severity

### SBP-001

- Rule ID: `FASTAPI-AUTH-001`, `FASTAPI-AUTH-002`
- Severity: High
- Location: [backend/app/api/v1/users.py](/Users/macow/personal-projects/mlb-app/backend/app/api/v1/users.py:130), [frontend/lib/api.ts](/Users/macow/personal-projects/mlb-app/frontend/lib/api.ts:106)
- Evidence:
  - `PushTokenPath = Annotated[str, Path(pattern=r"^ExponentPushToken\[.+\]$", description="Expo Push Token")]`
  - `@preferences_router.get("/{push_token}", ...)`
  - `@preferences_router.put("/{push_token}/players", ...)`
  - `` `/api/v1/preferences/${encodedToken(token)}` ``
- Impact: `push_token` を知っている第三者が、そのユーザー設定を読み書きできる。さらに URL パス運用のため、アクセスログや監視基盤にトークンが残りやすい。
- Fix: `push_token` を公開 API の認証子として使う設計をやめ、サーバー側で払い出すランダムなユーザー ID と署名付きトークン、または認証済みセッション / Bearer token に移行する。
- Mitigation: 直ちに全面移行できない場合は、少なくとも `push_token` を URL パスから除外して POST body / Authorization header に移し、読み書きエンドポイントに追加の署名検証を入れる。
- False positive notes: Expo push token 自体の推測は難しいが、漏えい時の被害範囲は明確であり、認証境界として使う設計は避けるべき。

### SBP-002

- Rule ID: `FASTAPI-AUTH-001`
- Severity: High
- Location: [backend/app/config.py](/Users/macow/personal-projects/mlb-app/backend/app/config.py:22), [backend/app/api/v1/router.py](/Users/macow/personal-projects/mlb-app/backend/app/api/v1/router.py:14), [backend/app/api/v1/test.py](/Users/macow/personal-projects/mlb-app/backend/app/api/v1/test.py:20)
- Evidence:
  - `enable_test_endpoints: bool = Field(default=False, validation_alias="ENABLE_TEST_ENDPOINTS")`
  - `if settings.debug or settings.enable_test_endpoints:`
  - `@router.post("/send-notification")`
  - `@router.post("/send-demo-notification")`
- Impact: 本番で `ENABLE_TEST_ENDPOINTS=true` にすると、認証なしで任意の Expo token へ通知送信を試せる。スパム送信やトークン存在確認に悪用されうる。
- Fix: テスト API は本番で無効を固定にするか、最低でも管理者認証・IP 制限・共有シークレットのいずれかで保護する。
- Mitigation: 緊急用途で残すなら、短時間だけ有効化し、運用後すぐに無効化する。監査ログも別途残す。
- False positive notes: `ENABLE_TEST_ENDPOINTS` を本番で絶対に使わない運用なら露出は限定されるが、コード上は有効化可能であり事故余地がある。

## Medium Severity

### SBP-003

- Rule ID: `FASTAPI-AUTH-001`
- Severity: Medium
- Location: [backend/app/api/v1/users.py](/Users/macow/personal-projects/mlb-app/backend/app/api/v1/users.py:63), [backend/app/api/v1/users.py](/Users/macow/personal-projects/mlb-app/backend/app/api/v1/users.py:133)
- Evidence:
  - `_get_or_create_user()` が `User`, `UserPlayer`, `UserEventPref`, `UserPlayerEventPref` を自動作成
  - `get_preferences()` が「未登録なら自動作成する」と明記されている
- Impact: 認証なしで valid-looking な `ExponentPushToken[...]` を大量に投げるだけで、ユーザーと関連設定レコードを増やせる。ストレージ消費や DB ノイズ、運用監視の悪化につながる。
- Fix: `GET /preferences` での自動作成をやめ、登録は `POST /users/register` のみに限定する。さらにレート制限を導入する。
- Mitigation: すぐに構造変更できない場合でも、IP 単位や token 単位の簡易レート制限を追加し、異常増加を監視する。
- False positive notes: 現状は push token 形式チェックしかなく、実在トークン確認は DB / Expo 送信時まで行われない。

## Fixed In This Pass

### FIX-001

- Location: [backend/app/services/notification.py](/Users/macow/personal-projects/mlb-app/backend/app/services/notification.py:20)
- Change: Expo Push API の `DeviceNotRegistered` を検出した token を自動で `users.is_active=false` に更新するようにした。
- Benefit: 無効 token への再送を減らし、不要な送信ノイズとエラー蓄積を抑えられる。

### FIX-002

- Location: [backend/app/services/notification.py](/Users/macow/personal-projects/mlb-app/backend/app/services/notification.py:83), [backend/app/api/v1/users.py](/Users/macow/personal-projects/mlb-app/backend/app/api/v1/users.py:105), [frontend/lib/api.ts](/Users/macow/personal-projects/mlb-app/frontend/lib/api.ts:21)
- Change: 通知送信ログから Expo の生レスポンスを出さないようにし、登録ログから token prefix を外し、クライアントの URL ログも `preferences/[redacted]` に置き換えた。
- Benefit: ログやクラッシュ収集基盤への token 露出を減らせる。
