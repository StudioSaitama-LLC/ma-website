# 間｜MA サイト — クライアント赤入れ PDF 修正ラウンド1 実装指示書

作成: 2026-08-02（メインセッション Fable による調査・指示書化）
対象 repo: `StudioSaitama-LLC/ma-website`（このファイルがある repo）
スペックの正: 本指示書。クライアント赤入れ PDF「間｜MA_Home_About_BVP_Final_Phone_RE」（スマホ版・21ページ）の全指示を文字起こし・構造化済み。PDF 原本は repo 外（発注者の手元）。

---

## Objective

クライアント（株式会社まなか）から入った赤入れ PDF の修正指示一式を実装する。
柱は5つ:

1. **ナンバリング体系の全面変更**（About を番号なしに、MA Lab=1 / MA Channel=2 / MA Do=3 へ繰り上げ、表示ルール統一）
2. **ヘッダー/メニューの挙動**（タイトル行の流れ消え、ナビ番号化、FORMA 風フェード、tei-ku 風メニューアニメーション）
3. **タイポグラフィ**（Helvetica Light + Noto Sans JP Light、太字廃止、半ツメ等）
4. **Home ファーストビュー**（カウンターのみ表示→スクロールで順次表示）
5. **文言・色・レイアウトの個別修正**（動画キャプション改名、フッター Company 移動、ロゴ50%縮小 ほか）

## Project Understanding

- 素の HTML/CSS/JS 6ページ構成。ビルドなし・全リンク相対パス。GitHub Pages（main ブランチ root）から https://studiosaitama-llc.github.io/ma-website/ で配信
- ページ: `index.html`（Home: カウンター/ポエム/CONTENTS 目次）、`about.html`、`ma-channel.html`（シリーズ一覧+UP DATE）、`edge-riders.html`（動画一覧）、`beyond-the-vanishing-point.html`（動画+記事抜粋）、`article-3-2-1.html`（随想記事）
- 共通: `css/style.css`（1ファイル・CSS変数でテーマ）、`js/main.js`（テーマ切替/ヘッダー scrolled/メニュー開閉/カウンター）
- 全ページに同一のヘッダー・メニューオーバーレイ・フッターが**コピペで重複**している（共通化の仕組みはない）。今回の共通変更は **6ファイル全部に同じ変更を入れる**こと（1ファイルだけ直して終わりにしない）
- テーマ: `html.light` クラス + CSS変数 + `localStorage("ma-theme")`（js/main.js:5-32）

## 表示ルール（今回の正準フォーマット・最重要）

PDF 内の赤枠で繰り返し指定されているルール:

```
数字␣␣英タイトル / 日タイトル
```

- 数字のあとは**半角スペース2つ**（現行の `&ensp;` は半角スペース2つに置き換えてよい。見た目が近ければ `&ensp;` 維持も可 — ただし全箇所で統一する）
- **太字にはしない**（現行 `.toc .lv1` の font-weight:700、`.series-ttl` の 700 は解除する）
- **英語タイトルが先、`/` を挟んで日本語タイトル**。丸括弧書き `(MA Channel)` 形式は廃止
- 番号を持たない項目（About MA）は `英タイトル / 日タイトル` のみ
- 根拠: PDF p1 のメニュー完成モック（`1 MA Lab / 間の定義化`、`2.2 Beyond the Vanishing point / 死を、教えてくれ。` 等、全項目がこの形式で描かれている）＋各ページに貼られた赤枠ルールボックス

## 新ナンバリング対応表（旧 → 新）

| 旧 | 新 | 表記（新） |
|---|---|---|
| 1 間とは何か？ About MA | （番号なし） | About MA / 間とは何か？ |
| 2 間の定義化 (MA Labo) | 1 | 1  MA Lab / 間の定義化 |
| 2.1 | 1.1 | 1.1  Dictionary / 感覚と感情の往復 |
| 2.1.1 平場で浮遊する感情 “感覚” | 1.1.1 | 1.1.1  “感覚” 平場で浮遊する感情（**"感覚"を前に**） |
| 2.1.2 オノマトペマップ “論理” | 1.1.2 | 1.1.2  “論理” オノマトペマップ（**"論理"を前に**） |
| 2.2 | 1.2 | 1.2  Reference Room / 間の資料庫 |
| 2.2.1〜2.2.4 | 1.2.1〜1.2.4 | 言葉/写真/映像/文章（そのまま） |
| 2.3 | 1.3 | 1.3  Research / 間の行動的実証 |
| 2.3.1〜2.3.3 | 1.3.1〜1.3.3 | 装置購入者の声/仮説検証ログ/間 do Flow |
| 3 間の流通化 (MA Channel) | 2 | 2  MA Channel / 間の流通化 |
| 3.1 | 2.1 | 2.1  Edge Riders / 密を往く者たち |
| 3.1.1〜3.1.3 | 2.1.1〜2.1.3 | ↓「動画キャプション改名表」参照 |
| 3.2 | 2.2 | 2.2  Beyond the Vanishing point / 死を、教えてくれ。 |
| 3.2.1 | 2.2.1 | 2.2.1  仁科 正史 (Pro Snowboarder/Artist) |
| 3.3 | 2.3 | 2.3  Traces in the Silence / 不在の風景 |
| 4 間の個人化 (MA Do) | 3 | 3  MA Do / 間の個人化 |
| 4.1〜4.4 | 3.1〜3.4 | 3.1  Inori / 祈りの道具・3.2  Kaori / 香り事業・3.3  Sosai / 葬祭事業・3.4  Boseki / 墓石事業 |

⚠️ 旧「2.x（MA Lab）」と新「2.x（MA Channel）」が**番号空間で衝突**する。sed 等の一括置換は絶対に使わず、ファイルごとに文脈を見て書き換えること。

### 動画キャプション改名表（番号変更と同時に文言も変わる）

| 新番号 | 新キャプション（旧キャプションから差し替え） |
|---|---|
| 2.1.3 | Flagship Store.　日々香好日 店舗初公開。築地の中心で、サムシングと叫ぶ。（旧: 宮嶋孝尚の、香から始まるサムシング。） |
| 2.1.2 | Gateway Shuffle.　間と死の関係的なサムシング。（旧: 間と死の関係的なサムシング。） |
| 2.1.1 | About Website MA　ウェブサイト「間｜MA」とは？（旧: 宮嶋孝尚が語る、web site 間。） |

- ma-channel.html の UP DATE 欄では**2行表記**（1行目: 番号+英タイトル、2行目: 日本語文）。行間のアキは詰める（下記「改行アキ」参照）
- edge-riders.html の動画カードでは1行（または折返し）でよい。既存リンク先は維持

## 変更詳細（ファイル別）

### 0. 全ページ共通（6ファイル）

**a. グローバルナビ（ヘッダー）**
- `--- ` プレフィックスを廃止（css/style.css:113 の `.global-nav .nav-item::before` を削除）し、番号を付ける: `1 MA Lab`・`2 MA Channel`・`3 MA Do`（HTML 側テキストに番号を追加）
- 現在ページを `<span>` にする既存パターン（ma-channel 系ページで MA Channel が span）は維持

**b. ヘッダータイトル行の「流れ消え」**
- 「上段のメニューバーは、流れるように上部に消えて欲しい」= スクロール時、サイトタイトル行が**上方向へスライドしながら**消える
- 現状はモバイルのみ `.site-header.scrolled .site-title` で opacity/max-height 切替（style.css:180-186）。これを**全ビューポート対象**にし、`transform: translateY(-100%)` + opacity のスムーズな transition に変える（ナビ行とハンバーガーは残る）
- ハンバーガーの「バランス調整」: タイトル行が消えた後もナビ・ハンバーガーの縦位置が崩れないよう整える（アイコンとナビの垂直センター合わせ）

**c. FORMA 風フェード**
- 「下のテキストがメニューバーにかかりそうになった時、緩やかに消えて欲しい」= スクロールで本文が sticky ヘッダーの下に潜り込む際、ヘッダー際で緩やかにフェードアウトして見える演出
- 実装は CSS `mask-image`（ヘッダー直下に透明グラデーション）方式を推奨（`body` ではなく `main` にかける等、position: sticky と干渉しない方法を検証すること）。JS の IntersectionObserver でも可。**依存ライブラリは追加しない**

**d. メニューオーバーレイ — アニメーション（tei-ku.com 風）**
- 現状は `display:none` ⇄ `flex` の瞬間切替（style.css:143,147）
- 参照サイト tei-ku.com の実装（調査済み）: メニューパネルが `transform: translateX` の **300ms ease-out** でスライドイン、ハンバーガー3本線が**×にモーフ**（1本目 translateY+rotate45 / 2本目 scaleX(0) / 3本目 translateY−+rotate−45）
- 本サイトは全画面オーバーレイなので: オーバーレイをフェード＋わずかなスライド（例: 上または右から）で開閉し、ナビ項目は**時差（stagger）付きでふわっと出す**。ハンバーガー→×モーフも実装（既存の `.menu-close` ボタンは残しても、ハンバーガー自体が×になるならそちらに寄せてよい）
- `display:none` のままだと transition が効かないので `visibility`/`opacity`/`pointer-events` 方式に変える。既存の開閉ロジック（ESC・リンククリックで閉じる、aria-expanded。js/main.js:44-72）は**必ず維持**

**e. メニューオーバーレイ — 構造改訂**（PDF p1 完成モックどおり）

```
HOME
1  MA Lab / 間の定義化            ← 工事中: 彩度落とし
  1.1  Dictionary / 感覚と感情の往復
  1.2  Reference Room / 間の資料庫
  1.3  Research / 間の行動的実証
2  MA Channel / 間の流通化
  2.1  Edge Riders / 密を往く者たち
  2.2  Beyond the Vanishing point / 死を、教えてくれ。
  2.3  Traces in the Silence / 不在の風景   ← 工事中: 彩度落とし
3  MA Do / 間の個人化             ← 工事中: 彩度落とし
About MA / 間とは何か？
Contact us
Company
```

- 「（現在工事中）」という**文字は排除**し、工事中の項目は**彩度を落として表示**（既存 `.dim` の muted 色流用でよい。リンク先がないものは現行同様アンカーのみ）
- リンク先: 2.1→edge-riders.html、2.2→beyond-the-vanishing-point.html、2 全体→ma-channel.html、About→about.html、1/3→index.html 内アンカー（既存 #ma-lab / #ma-do を維持）。1.1〜1.3 と 2.3 はページ未存在なので非リンク

**f. フォント**
- `--sans` を変更: 英数字が Helvetica Light で出るよう `"Helvetica Neue", Helvetica, Arial, "Noto Sans JP", "Hiragino Kaku Gothic ProN", sans-serif` の順に（style.css:19）。ウェイトは Light(300) 基調（現行 body 300 は維持）
- 意図: 「英: Helvetica - Light / 日: Noto Sans JP - Light。できなければ各端末で一番綺麗に見える最もスタンダードなゴシック系ライトウェイト」

**g. ロゴ 50% 縮小**
- `.logo-mark` width 120px→60px、モバイル 90px→45px（style.css:249-263）。全ページ共通

**h. フッター**
- Company リンクを Contact us の**隣（右側グループ）**へ。デスクトップは既に `.footer-links` に両方あるので、モバイルの `justify-content: space-between`（style.css:629-633）をやめて**右寄せで2つ並べる**（Company が左端に離れて見えるのが赤入れ対象）
- 並び順は `Company` `Contact us`（PDF p6 の矢印どおり Company が Contact us の左）

**i. 太字の廃止**
- 表示ルール「太字にはしない」に伴い `.toc .lv1`（style.css:277 font-weight:700）と `.series-ttl`（style.css:450 font-weight:700）を 400〜500 程度に落とす。数字含め見出しの 700 は使わない

**j. 左右余白の共通化**
- 「※共通 左右の余白」: 全ページで左右余白が揃っていることを確認し、ズレがあれば `.page` / `.content` のパディングに統一（現状 `.content` の `margin-left: clamp(...)` はモバイルで 0。大きな構造変更は不要、目視で揃っているかの確認と微調整）

**k. `<title>` / OGP の番号更新**
- 各ページの `<title>`・`og:title`・`og:description` 内の旧番号/旧表記も新体系に合わせて更新する

### 1. index.html（Home）

- **ファーストビュー**: 「HOME ではまず、ここ（カウンター）だけを表示させたい。他はスクロール後に表示させていく」
  - カウンター部を高さ 100vh（`100svh` 推奨）のヒーローとし、**センター配置**（モバイルの `align-items: flex-start`（style.css:229-231）もセンターに変更）で**フェードイン**
  - `.content`（ポエム以下）はスクロールに応じて順次フェードイン表示（IntersectionObserver + CSS transition。ポエムの「スクロールすると、テキストが読める」もこの一環）
- **カウンター数字の半ツメ**: 現在 `letter-spacing: 0.28em` + JS が数字間に半角スペースを挿入（js/main.js:78 `split("").join(" ")`）。スペース挿入をやめ、letter-spacing をおよそ半分（0.12〜0.15em 程度）に詰める。カウントアップ演出（0→2）は維持
- **TOC 全面改訂**: 上記対応表・表示ルールどおり（index.html:84-125）
  - `1&ensp;間とは何か？ <a>About MA</a>` → 番号なし `<a href="about.html">About MA / 間とは何か？</a>`
  - MA Lab ブロック（新1系）: 「（現在工事中）」の `note-jp` を削除し、ブロック全体（1、1.1〜1.3.3）を彩度落とし表示
  - 3.2 の `link-pink`（index.html:109）を**廃止し通常のグリーンリンク**に（style.css:317 の `.link-pink` も削除）
  - `<NEW>` バッジは 2.1 と 2.2 に維持
  - `.sub` 行（キャッチコピー）の上アキを詰める（style.css:292-296 の margin 調整。「ここの改行はアキを少なくして」）
  - `id="ma-lab"` / `id="ma-do"` アンカーは新しい 1 / 3 の行に付け替えて維持

### 2. about.html

- h1 `・間とは何か？ <span class="en">(About MA)</span>` → `About MA / 間とは何か？`（**中黒「・」削除**・番号なし・ルール形式）
- 冒頭の「〇〇〇…」プレースホルダーは**そのまま残す**（「怪文書待ち」= クライアント入稿待ち。創作して埋めない）
- 「・核となる二項…」「・間を定める、広める、感化する」等の本文中見出し・本文・図は変更しない

### 3. ma-channel.html

- h1 → `2  MA Channel / 間の流通化`
- series 3ブロックを新番号・ルール形式に（対応表どおり）。UP DATE 欄のエントリは動画キャプション改名表どおり2行表記＋番号更新
- 2.2.1（仁科）の日付は `26/01/01`。他エントリの `26/00/00` は**そのまま**（実日付未確定）
- リンク先（edge-riders.html / article-3-2-1.html → リネーム後パス）は維持・追随

### 4. edge-riders.html

- h1 → `2.1  Edge Riders / 密を往く者たち`（中黒削除）
- 動画3枚のキャプションを改名表どおり更新（edge-riders.html:77,86,95）
- note 抜粋・「note を読む ↗」ボタンは現状維持

### 5. beyond-the-vanishing-point.html

- h1 → `2.2  Beyond the Vanishing point / 死を、教えてくれ。`（中黒削除）
- 関連動画カード（1枚目、beyond-the-vanishing-point.html:76-84）の**手前に「関連動画：」ラベルを挿入**
- 同カードの表記を `密を往く者たち Edge Riders` + `3.1.2 間と死の…` の2行から → `2.1.2  Gateway Shuffle.　間と死の関係的なサムシング。` に差し替え（edge-riders.html へのリンクは維持）
- 2枚目カード: 日付 `26/01/01 <NEW>`、`2.2.1  仁科 正史 (Pro Snowboarder/Artist)` — **仁科の行はリンクなし・白色（通常テキスト色）に**（記事への導線は既存の「随筆記事を読む ↗」ボタンが担う）

### 6. article-3-2-1.html → article-2-2-1.html

- `git mv` で `article-2-2-1.html` にリネームし、参照元（ma-channel.html / beyond-the-vanishing-point.html）を全て更新（`grep -rn "article-3-2-1"` で取りこぼし確認）
- 旧パス `article-3-2-1.html` には新パスへの `<meta http-equiv="refresh">` + canonical のスタブ HTML を残す（旧 Vercel URL などからの被リンク切れ防止。GitHub Pages はサーバーサイドリダイレクト不可のため）
- ページ内: `<title>`・`og:title`・h1 の `3.2.1` → `2.2.1`、日付 `26/00/00` → `26/01/01`
- 記事本文・写真は**一切変更しない**

## Behaviors To Preserve（壊してはいけない既存挙動）

- テーマ切替（Light/Dark、`localStorage("ma-theme")` 永続化、`html.light` の全 CSS 変数、ロゴの `filter: invert(1)`）
- カウンターのカウントアップ演出（`data-count="2"` → 0 から 260ms 刻み）
- メニュー開閉: ESC で閉じる、リンククリックで閉じる、`aria-expanded` 同期、閉時に開ボタンへフォーカス返し
- ページ内アンカー `index.html#ma-lab` / `#ma-do` の到達性
- `<NEW>` バッジの7色サイクルアニメーション（animation-delay による色ずらし含む）
- note-btn / 外部リンク（YouTube・note）の遷移先
- **全リンク相対パスのまま**（GitHub Pages のプロジェクトページ配下 `/ma-website/` で動くこと。ルート絶対パス `/...` を書かない）
- 記事本文・ポエム・リード文などの日本語本文（指示があった箇所以外、一字も変えない）
- OGP・favicon・meta description の存在（文言は番号更新のみ）

## Non-Negotiables

- ビルドツール・フレームワーク・外部 JS/CSS ライブラリを導入しない。素の HTML/CSS/JS を維持
- `js/main.js` と `css/style.css` の1ファイル構成を維持（分割しない）
- 一括置換（sed 等）で番号を書き換えない（旧2.x と新2.x が衝突するため）
- 無関係な整形・リファクタリング・「ついで」変更をしない
- ヘッダー/メニュー/フッターの共通変更は**6ファイル全てに同一適用**（適用漏れは不合格）

## Stop And Ask Conditions（実装を止めて質問する条件）

1. About 冒頭のプレースホルダーを埋めるコピー（怪文書）— **創作しない**。入稿があるまでプレースホルダー維持
2. `26/00/00` の実日付 — 2.2.1 の `26/01/01` 以外は確定情報がない。勝手に埋めない
3. 表示ルールを適用すると不自然になる箇所（英タイトルが存在しない項目など）で対応表に載っていないものが出たら
4. tei-ku 風アニメーションの実現にライブラリ追加が必要だと感じたら（→ 原則 vanilla で近似。追加はしない）
5. FORMA 風フェードで sticky ヘッダーとの両立がどうしても崩れる場合の代替案採用
6. この指示書と実ファイルの記述が矛盾していたら

## Baseline Commands

作業開始時に必ず:

```bash
git status                 # クリーンであること・ブランチ確認
python3 -m http.server 8000  # ルートで起動し、全6ページをブラウザで表示確認
```

- ビルド/テスト基盤はない。**検証はブラウザ目視＋grep** が全て
- baseline として修正前の全ページの表示（特にモバイル幅 375px。赤入れ PDF はスマホ版）を確認・記録してから編集に入る

## Implementation Phases

小さく・戻しやすく。**フェーズごとにコミット**（コミットメッセージは「なぜ」を書く。Phase X などの内部符号は使わない）。

1. **Baseline**: サーバー起動、全ページ確認、git status 記録
2. **ナンバリング・文言改訂**（静的テキスト変更のみ。挙動に触らない）: 対応表・改名表・ルール形式を index → ma-channel → edge-riders → bvp → article（リネーム含む）→ about の順に。`grep -rn "3\.1\|3\.2\|4\.1\|MA Labo\|現在工事中\|article-3-2-1"` 等で取りこぼし確認
3. **タイポグラフィ・装飾**: フォントスタック、太字解除、ロゴ50%、工事中の彩度落とし、link-pink 廃止、半ツメ、フッター Company 移動、改行アキ詰め、余白確認
4. **ヘッダー挙動**: `---` 除去＋ナビ番号、タイトル行の流れ消え（全ビューポート）、FORMA 風フェード
5. **メニューオーバーレイ**: 構造改訂（ツリー化＋工事中彩度落とし）→ tei-ku 風アニメーション（stagger・ハンバーガーモーフ）。既存の開閉/ESC/フォーカス挙動の回帰確認
6. **Home ファーストビュー**: ヒーロー化・カウンター中央フェードイン・スクロール順次表示
7. **最終検証 → PR**（下記 Verification 全項目）

## Verification Requirements

全て完了後、以下を実施し結果を報告に含める:

- [ ] 全6ページ＋リダイレクトスタブをローカルサーバーで表示、コンソールエラーなし
- [ ] モバイル幅（375px）とデスクトップ幅の両方で確認（赤入れはスマホ版が基準）
- [ ] Light/Dark 切替が全ページで機能・永続化
- [ ] メニュー: 開閉アニメーション、ESC、リンククリック閉じ、aria-expanded
- [ ] `index.html#ma-lab` / `#ma-do` アンカー到達
- [ ] カウンター: センター配置・フェードイン・半ツメ・カウントアップ
- [ ] スクロール: タイトル行の流れ消え、本文のヘッダー際フェード、Home の順次表示
- [ ] `grep -rn "article-3-2-1" *.html` が スタブ以外 0 件
- [ ] 旧番号の残骸 0 件（`3.1`〜`3.3`・`4.1`〜`4.4`・`(MA Labo)`・`（現在工事中）` を grep。新 3.1〜3.4=MA Do 系との混同に注意して目視判定）
- [ ] 相対パスのみ（`grep -rn 'href="/\|src="/'` が 0 件）

## Reporting Format

完了報告には以下を含める:

1. 実行した検証コマンドと結果（上記チェックリストの充足状況）
2. ファイル別変更サマリ（機能単位で。行数自慢は不要）
3. 実装しなかった/保留した項目とその理由（Stop-and-ask に該当したものを含む）
4. PR: main 向け。リポジトリの PR フォーマット（なぜ作ったか/何を入れたか/設計判断/スコープ外/検証方法/依存）に従う。**main へ直 push しない**

## Out-of-scope Items（今回やらない）

- 怪文書（About 冒頭コピー）の作成・流し込み — クライアント入稿待ち
- `26/00/00` プレースホルダー日付の実日付化（2.2.1 の 26/01/01 のみ今回反映）
- 動画プレースホルダーへの実動画（YouTube 埋め込み）差し込み
- Company / Contact us ページの新設（リンク先は現状 `#` のまま）
- MA Lab（Dictionary / Reference Room / Research）・Traces in the Silence の各ページ新設
- 旧 Vercel プロジェクト（ma-website-pied.vercel.app 系）の整理・削除
- HTML の共通部品化（テンプレート化）— 今回はコピペ構成のまま6ファイル同期で対応
