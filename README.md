# Bokutachi IR Tracker

※注意  
完全に自分のためのツール・DeepSeek V4 Proにて生成されたコード

Bokutachi（BMSスコア管理ツール）のAPIを利用し、1日のランプ・BP・EXスコア更新を一覧表示するCLIツール。

## インストール

```bash
git clone https://github.com/light1192/BokutachiIR-Tracker.git
cd BokutachiIR-Tracker
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# 画像出力を使う場合のみ
pip install playwright
playwright install chromium
```

## 使い方

```bash
source .venv/bin/activate

# ユーザー名でIDを検索
python3 bokutachi_tracker.py --find-user-id <ユーザー名>

# 今日の更新（ID直指定）
python3 bokutachi_tracker.py -u <ユーザーID>

# 日付指定
python3 bokutachi_tracker.py -u <ユーザーID> --date 2026-05-26

# BMS-7Kのみ
python3 bokutachi_tracker.py -u <ユーザーID> --games bms-7k

# 画像出力
python3 bokutachi_tracker.py -u <ユーザーID> --date 2026-05-26 --image-lamp lamp.png
python3 bokutachi_tracker.py -u <ユーザーID> --date 2026-05-26 --image-updates updates.png
python3 bokutachi_tracker.py -u <ユーザーID> --date 2026-05-26 --image-sessions sessions.png
python3 bokutachi_tracker.py -u <ユーザーID> --date 2026-05-26 --image all.png
```

## 出力例

```
────────────────────────────────────────────────────────────
  BMS-7K — 2026-05-26  (30 plays)
────────────────────────────────────────────────────────────
  ランプ更新: 11曲  /  BP更新: 12曲  /  EX更新: 19曲

  ◆ セッション

    Session #285: Plump Attached Lack  (Lamp:11, BP:17, EX:24)
        1. Kirby in Luminous Land(short ver.) [sl7] ★2142 @ 17:29 [LAMP,BP↓,EX↑]
           Lamp: HARD CLEAR, EX: 3968 (92.62%), BP: 21
        ...

  ◆ クリアランプ更新 (11)

    ── EX HARD CLEAR ──
    1. Forty-Four[INSANE] [st0 重0] ★3740 @ 17:49 [LAMP]
       Lamp: EX HARD CLEAR, EX: 6719 (89.83%), BP: 25
    ...

    ── HARD CLEAR ──
    1. Kirby in Luminous Land(short ver.) [sl7] ★2142 @ 17:29 [LAMP]
       Lamp: HARD CLEAR, EX: 3968 (92.62%), BP: 21

    ── CLEAR ──
    1. endlessky [sl12 ▼16] ★1723 @ 17:44 [LAMP]
       Lamp: CLEAR, EX: 2768 (80.33%), BP: 50

    ── EASY CLEAR ──
    1. 永劫の沙漏 <秒-> [st6 dl6] ★3070 @ 19:26 [LAMP]
       Lamp: EASY CLEAR, EX: 4139 (67.41%), BP: 257
    ...

  ◆ BP更新 (12)
    1. 永劫綺譚の純潔葬花 -Black Lily- [st6 双5] ★2980 @ 18:56 [BP↓]
       Lamp: FAILED, EX: 4418 (74.13%), BP: 196
    ...

  ◆ EX更新 (19)
    1. 永劫綺譚の純潔葬花 -Black Lily- [st6 双5] ★2980 @ 18:56 [EX↑]
       Lamp: FAILED, EX: 4418 (74.13%), BP: 196
    ...
```

## 仕組み

- Bokutachi API のみを使用（読み取り専用、スコア送信なし）
- セッションAPIの `deltas` + `isNewScore` + PBの `composedFrom` で改善を正確に検出
- キャッシュ不要、前日比較不要

## Webツール

`index.html` をブラウザで開くだけ。サーバー不要。

- ユーザー名 or ID を入力 → Load
- タブ切替: All / Sessions / Lamp / BP / EX
- 日付選択可能

| オプション | 内容 |
|------------|------|
| `--image-lamp` | ランプ更新のみ |
| `--image-updates` | ランプ+BP+EX更新 |
| `--image-sessions` | セッションログ |
| `--image` | すべて |
