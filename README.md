# 間｜MA — ma-website

Indies Lifestyle Media 間｜MA のウェブサイト（株式会社まなか × Studio Saitama）。
静的 HTML/CSS/JS 構成。GitHub Pages で公開する。

- 公開URL: https://studiosaitama-llc.github.io/ma-website/
- 関連リポジトリ: [ma-jpn](https://github.com/StudioSaitama-LLC/ma-jpn)（旧サイト / GitHub Pages。本 repo とは別系統）
- 企画・戦略ドキュメント: `studiosaitama/clients/manaka/docs/`（ローカル）/ [manaka-docs](https://github.com/StudioSaitama-LLC/manaka-docs)

## 構成（2026-10 β版から）

ページは `src/` のデータから `tools/build.py` が生成する。**生成された HTML を直接直さない**（次の生成で消える）。

```
src/                           # 直すのはここ
  site.json                    # サイト名・門（name・short・ja・plain）と扉・Home の言葉・News・Notion の図の言葉・見方の一言（views）・お店の一覧・値段の表示
  programs.json                # 番組（間を、喰う／死を、教えてくれ。／異能の表現者たち）と回（ゲストごとのまとまり。並びが #1, #2 … の番号になる）
  contents.json                # コンテンツ（#2-1-3 など。種類・番組・回・状態・YouTube・記事）
  manifesto.json               # Notion のマニフェスト（tools/import_manifesto.py で docx から作る）
  device.json                  # Device の商品（tools/import_device.py で荒井さんの Device 表から作る）
  company.json                 # Company（まなかの軌道・会社概要・運営施設）と Contact の窓口。運営施設は {"name", "url"}（url が無いものは本文の色で出す）
  articles/*.html              # Magazine 記事の本文（HTML の断片。画像の @/ はサイトの最上位。article-head の中に日付の目印 <!-- build:meta --> を置く）
  lab.json                     # Lab の試作データ（要素・用語・資料・検証のテーマ）
tools/
  build.py                     # src/ → 公開用 HTML（標準ライブラリだけ・Python 3.9 以上）
  import_manifesto.py          # Notion の docx → src/manifesto.json
  import_device.py             # Device 表の xlsx → src/device.json
  import_youtube.py            # YouTube の題と説明文の冒頭 → src/contents.json の yt_title・yt_lead
  import_article.py            # Magazine の原稿（Word を Google ドキュメントで .html に書き出したもの）→ 記事の断片と contents.json
  generated.txt                # build.py が生成したファイルの一覧
css/ js/ assets/               # 見た目と画像（assets/device/ は Device の写真、assets/illust/ は手描きの絵）

# 生成されるページ（URL）
index.html                     # Home（このサイトの一言と「最新の回を観る」・4 つの門の地図・News）
notion/                        # Notion（マニフェスト・密と間・三段の図と式）
lab/                           # Lab（試作。dictionary/ reference/ research/ の 3 部屋）
channel/                       # Channel（番組のカード・紹介文・News。News は回の単位）
channel/<番組>/                # 番組のページ（第 0 回＝企画背景と、回のカード。#ep-<回> はその回のカード）
channel/<番組>/<回>/           # 回のページ（動画・読む・聴く・出てくる道具・映っている間・次の一歩）。回を決めていないコンテンツは番号が <回> になる
channel/<番組>/<番号>/         # Magazine 記事（後ろに「同じ回を、ほかの形で」と次の一歩）
do/                            # Do（開いている扉が Device だけの間は do/device/ へ転送）
do/device/                     # 道具の一覧（道具が 10 に満たない間は検索とお店の絞り込みを出さない）
do/device/<お店>/<商品ID>/     # 商品のページ
company/  contact/             # Company / Contact
about.html ほか 8 月版のページ   # 新しいページへ転送するだけのページ
```

### `src/contents.json` の項目

| 項目 | 中身 |
|---|---|
| `id` | 番号。`2-1-3` の形（2.1 TV・2.2 Magazine・2.3 Radio）。重複不可 |
| `kind` | `tv` / `mag` / `radio` |
| `program` | `programs.json` の `slug` |
| `episode` | `programs.json` の回の `key`（同じゲストの TV・Magazine・Radio をまとめる）。無ければ 1 件で 1 回 |
| `date` | 公開日（`YYYY-MM-DD`）。無ければ回（`programs.json` の episodes）の日付を引き継ぐ。Home の News には公開済みの回だけが新しい順に 3 件まで出る。`<NEW>` は日付の新しい 3 つのうち、いちばん新しい日付から 60 日以内のものに付く |
| `status` | 必須。`published`（公開）/ `editing`（編集中）/ `planned`（掲載予定）。公開以外は、画面ではどちらも「準備中」と出し、押せない形にする |
| `title` `caption` `badge` `place` `recorded` | 表示する題・ひとこと・記事の種類・場所・収録日（`YYYY-MM-DD`） |
| `youtube` | YouTube の動画 ID（11 文字）。公開のときだけ埋め込む |
| `yt_title` `yt_lead` | YouTube の題と、説明文のうち「TIMELINE」の見出しか、時刻で始まる行が 2 行続く所より前（`tools/import_youtube.py` が公開の動画だけ書く。手で直さない）。あれば回の題と一言はこれを使う（題・一言を YouTube にいつも合わせるため）。説明文が空なら `caption` が一言になる |
| `article` | Magazine の本文（`src/articles/` の断片）。公開のときだけ記事ページを作る。`episode` か `prologue` が要る（無いと回のページと住所が重なるので `build.py` が止まる）。題の頭の管理番号（2.2.1 など）は画面に出さない（本文が取れないと `build.py` が止まる） |
| `excerpt` | 記事がまだ無いときの冒頭（いまは画面に出さない。原稿の取り込みの控え） |
| `words` | 書き手（Words）。見方のカードに出す |
| `device` | このコンテンツに出てくる商品 ID の並び（例 `["2"]`）。回のページの「出てくる道具」と、商品ページの「出てくる回」に出る。無ければ出さない |
| `redirect_from` | この記事へ転送する 8 月版の URL |
| `hero` `portrait` `portrait_focus` | 記事の冒頭で切り替わる写真（`assets/` の名前の並び）・記事の終わりに画面いっぱいに出す人物の写真・その切り抜きの中心（例 `"68% 50%"`） |
| `prologue` | 番組の第 0 回（企画背景）なら `true`。回には入れず、番組ページの回の一覧の先頭に出す（`episode` は書かない） |
| `related` | 旧版の「関連コンテンツ」の印。改訂版では使わない（書くと `build.py` が止まる。回なら `episode`、番組の第 0 回なら `prologue`） |
| `memo` | 作業用のメモ。ページには出ないが、この repo は公開なので人に見せられないことは書かない |

`build.py` は生成の前にこれらを検査し、綴り違い・未登録の番組・画像の置き忘れがあると止まる。

Device の写真は `assets/device/` にファイル名のまま置く（Device 表の「メイン画像」「特徴 N 画像」の名前と一致させる）。

### 見た目について（2026-10-16 版デザイン）

- 荒井さんの PC / Phone の PDF（10/16）に合わせている。色は青地（`#1414dc`）に白、リンクと選ばれている所は水色。フッターの切り替えで灰地になる
- 寸法は スマホ 375px と PC 1920px のデザインの位置に合わせた。PC の寸法は画面の幅 1200px 以上で使う。481〜1199px（タブレットなど）はデザインが無いので、スマホの寸法のまま 480px の列にして中央に置く。360px 未満の小さい画面は、ページ全体を 0.8533 倍に縮めて組む（320px でちょうど 375px の組みになる。そのため 360px の前後で文字の大きさが少し変わる）
- 章（Notion・Company）は HTML の時点で閉じてあり、章の題（右に ＋）を押すと `js/main.js` が開く（開くと −）。JavaScript が切ってある画面では全文を出すが、`js/main.js` だけが読み込めなかったときは閉じたままになる
- `assets/illust/` の手描きの絵（8 点）は SVG。デザインの高解像度の描画から線をなぞって作った。差し替えるときの取り決め:
  - 先頭の `<svg>` に `viewBox`、絵の本体は `<symbol id="art" viewBox="…">` の中に入れる（ページは `<use href="…#art">` で呼ぶ）
  - 色は `fill="currentColor"` にする（青地では白、灰地では黒になる）
  - 取り決めに合わないと `build.py` が止まる
- `assets/figures/` の「密」「間」の球（Notion）は、デザインの描画から球の中心と大きさを測って `tools/make_spheres.py` で作った SVG（光は右上から・下に影）
- 生成した HTML にある `data-m` / `data-mt` は、デザインの位置と比べる採寸用の目印（表示や動きには使っていない）
- **Lab は試作**。`src/lab.json` に用語（Dictionary）・資料（Reference）・検証のテーマ（Research）を書く。
  置き方の決まり: どの項目も、マニフェスト（`src/manifesto.json`）の章 `ch`（整数）と、その本文に一字一句そのまま含まれる
  8 字以上の一節 `quote` を持つ（無ければ `build.py` が止める）
  - 要素 `elements`: マニフェストの考えを分解したもの。`key`・`name`（6 字まで。地図の札に入れる）・`sub`（一言）・
    `mitsu`（密の側の姿）・`ma`（間の側の姿。本文に無い言い換えは `guess` に `"mitsu"` / `"ma"` を書くと ※ が付く）・`ch` と `quote`・`acts`（マニフェストの羅列から、この要素に当たる行い。Lab の見立て）。
    用語・資料・検証は `elements` でこの `key` を引く。資料が 1 つも無い要素があると止める
  - 用語 `terms`: `key`（英小文字）・`word`・`reading`・`kind`・一般の意味 `gloss`・マニフェストでの使われ方 `sense`（本文に書いてあることだけ）・
    `onomatopoeia`（手がかりの語の並び）・`related`（他の用語の `key`）・`question`。`acts` は本文の羅列を写すとき
  - 資料 `references`: `id`（英小文字。年は入れない）・`form`（`forms` のどれか）・`field`・`title`・`creator`・`year`（文字列）・
    `terms`（用語の `key`）・`elements`（映っている要素。`相談中` 以外は 1 つ以上）・なぜ置くか `why`・`question`・`pole`（0 が密、100 が間）・`status`・`note`。
    `status` は **確認済み**（本は書誌を国会図書館・CiNii・版元で、作品・展覧会・標語は初演・初出・開催年を公開情報で確かめ、PR に確認先を残した）／**候補**（まだ確かめていない）／**相談中**（載せ方を決めていない）
  - 検証 `research`: `id`・`theme`・`lines`・`terms`・`status`。こちらの `status` は Channel と同じ `published / editing / planned`
  - `doors` は扉の副題 `ja` と役割 `role`（英名は `site.json` の gates）。`poles` は目盛りの両端の名前
- ページの上の段: サイト名の段はスクロールで流れて消え、門の名札の段は上端まで来たら貼り付く。その下に重なる本文はゆるやかに地の色へ消える。メニューのボタンは右上に残る
- Home の「現在、／1／人が平場に立ちました。」は、最初の画面の下にこのサイトの一言と「最新の回を観る」が見える高さにしてある
- Home の Ryan Gander の引用は、掲載の可否を確かめてから `src/site.json` の `quote.lines` に入れる（空のあいだは欄ごと出さない）

### 言葉と部品の決まり（2026-10 改訂）

- 水色（`--accent`）は押せるものだけに使う。見出し・いまいる門・記事の種類の札には使わない（いまいる門は線の札）
- 押せるものの形は 3 つ: 文字リンク、ボタン（`btn-primary`。1 画面に 1 つ）、カード（枠ごと押せて右下に →）。外のサイトは ↗、その場で開くものは ＋／−。↓↑ の矢印のボタンは使わない
- 1 枚のカードに行き先は 1 つ。カードの中に別のリンクを入れない。準備中は灰色の破線で押せない形（状態の言葉は「準備中」の 1 つ）
- 部品（`tools/build.py`）: 名札（`header`・`menu`・`gate_head`）・番組カード・回カード・見方カード（動画・随想記事・編集後記・音声）・道具カード・要素の札・状態の札・次の一歩。どのページもこの組み合わせで作る
- 画面に管理番号（2-2-4 など）と「Gate n: / Door n-n:」を出さない。回は「#1 仁科 正史」のように番組の中の番号と人で呼ぶ（番号は `programs.json` の並び。企画背景は #0）。台帳と URL では番号を使い続ける
- 門は名前（Notion・Lab・Channel・Do）と短い一言（考え方・研究室・番組・道具）の名札。門のページの見出しは名前といまの言葉（間、定義化への試み など）の 2 段で、平易な説明（`plain`）はその下に置く。扉は英語の短い名前（Dictionary・TV・Device など。Space・Station・Room は付けない）
- 見方の一言は「いつを、誰の目で」の対にそろえる（`site.json` の `views`。例 随想記事「撮影の日を、聞き手の目で」・編集後記「撮影までを、作り手の目で」）。一言に「読む」を付けない。書き手は `words` で Words の行に出す
- 見出しはページの主語を繰り返さない（回のページは「読む・聴く」「出てくる道具」「映っている間」、記事の後ろは「同じ回を、ほかの形で」）
- 回のページの見出しは YouTube の題に揃える（題に「」が入っているときの『』囲みは、カードでは使わない）
- 要素の札（回の `elements`・商品の `elements` に Lab の要素の `key` を並べる）は、付けたときだけ出す。どの回・道具にどの要素を付けるかはまなか側が決める
- 商品の値段は Device 表では税抜なので、`src/site.json` の `price` の決まりで税込にして出す（総額表示）

## 更新のしかた

```bash
python3 tools/build.py            # src/ から生成し直す
python3 tools/build.py --check    # 生成結果と repo のファイルが一致するか確かめる
```

マニフェストや Device 表の新しい版が届いたとき:

```bash
python3 tools/import_manifesto.py <Notion_YYYYMMDD.docx>
python3 tools/import_device.py <Device_YYYYMMDD.xlsx> --ids 2
python3 tools/build.py
```

Magazine の原稿（Word）が届いた・直ったとき（記事と題・冒頭はいつも原稿に合わせる）。原稿を Google ドキュメントで開き「ファイル → ダウンロード → ウェブページ」で書き出して渡す:

```bash
python3 tools/import_article.py <原稿.html> --id 2-2-4 --article src/articles/2-2-4.html \
    --photo "1_○○.jpg=ep224-1.jpg" --alt "ep224-2.jpg=写真の説明"   # 公開する記事（写真は assets/ に置いてから）
python3 tools/import_article.py <原稿.html> --id 2-2-3 --meta-only   # 掲載予定: 題と冒頭 4 行だけ
python3 tools/build.py
```

原稿の決まり（まなかの Word のひな形）: 冒頭の写真 → 記事の種類 → 「YYYY/MM/DD MA Magazine/2-2-N」 → 副題 → Place / Words / Photo → 赤字の「(記事タイトル:)」の次の行が記事のタイトル → 本文（太字の行は見出し、「(写真: ○○)」と赤字の「（写真キャプション）」）。赤字はページに出さない。最後の行の写真は記事の終わりに画面いっぱいに出す。

YouTube の題や説明文を変えたとき（回の題と一言はいつも YouTube に合わせる）:

```bash
python3 tools/import_youtube.py --check   # ずれている動画を出すだけ
python3 tools/import_youtube.py           # contents.json の yt_title・yt_lead を書き換える
python3 tools/build.py
```

PR と main への push では、GitHub Actions（`.github/workflows/check.yml`）が `tools/build.py --check` を実行する。
src/ を直して生成し忘れた PR や、生成された HTML を直接直した PR はここで失敗する
（マージを止めるには、main の保護設定でこの確認を必須にする）。

ローカル確認は任意の静的サーバーで（`channel/` のような URL はファイルを直接開くと一覧表示になるため、サーバー経由で見る）:

```bash
python3 -m http.server 8000
```

main への直 push は禁止。ブランチ → PR でマージする（Pages は main から自動配信）。
β版の間（一般公開を決めるまで）は `src/site.json` の `noindex` を `true` にしておく。

## Provenance（archived-from）

- 初期ファイル一式はデザイナー制作の静的書き出しを Google Drive 経由で受領したもの（2026-07-27 受領 / `drive-download-20260727T043816Z-1-001/ma-website`）
- git 管理化（2026-08-02）以前は Vercel に CLI 直デプロイで公開されていた:
  - https://ma-website-pied.vercel.app/ （受領ファイルと同一内容の先行デプロイ）
  - Vercel チーム `studiosaitama-llc` の `ma-website` プロジェクト（Git 連携なし・最終デプロイ 2026-07-29 は ERROR）
- 本 repo 化以降は GitHub Pages を正とする
