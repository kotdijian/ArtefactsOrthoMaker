# ArtefactsOrthoMaker (旧 Artifact Pose Normalizer)

OBJ / PLY / GLB 形式の考古資料3Dモデルを読み込み、**土器**または**石器**として姿勢・座標系を正規化し、正規化モデル、変換行列、オルソ画像、輪郭線、断面図を作成する Python GUI アプリです。

姿勢推定・座標系正規化（pose_core.py）をベースに、オルソ投影展開図作成用アプリとしてアップグレードしました。

現在の正式実行ファイルは **`app.py`** です。v0.1.x 系で完成した土器機能と、v0.2–0.3 系で追加した石器機能を統合しています。`APP_VERSION` は `0.4.2` です。

**注意事項：このリポジトリをZIPでダウンロードするか、Cloneしてください。**

**app.pyだけを単独でダウンロードしないでください。pose_core.py と requirements.txt も必要です。**

## ドキュメント内ナビゲーション

- [共通仕様](#common)
- [土器版](#pottery)
- [石器版](#lithic)
- [計測データ CSV](#measurements)
- [出力ファイルと Transform](#outputs)
- [Python 環境・実行方法](#environment)

---

<a id="common"></a>
# 共通仕様

## 1. 入力とモデル種別

起動ディレクトリの `input/` にモデルを置きます。

対応形式：

```text
.obj
.ply
.glb
```

STL は対象外です。

OBJ は参照される MTL / JPEG 等の外観情報を可能な範囲で利用します。PLY の vertex color、GLB の appearance にも対応します。

GUI の `モデル種別` で選択します。

```text
モデル種別 [ 土器 / 石器 ]
```

デフォルトは `土器` です。モデル読込後に種別を変更してもメッシュを再読込する必要はありませんが、姿勢決定状態はリセットされます。

## 2. 入力単位

```text
入力単位 [ mm / cm / m ]
```

単位設定は、面間隔、スケールバー、SVG の物理寸法等を mm に換算するために使います。**モデルの数値座標そのものを mm にリスケールする処理は行いません。**

例：座標値 `1.0` が 1 m を意味するモデルでは `m` を選択します。

## 3. 入力キューと処理済み判定

- `input/` 内の対応ファイルをファイル名昇順で処理
- `output/<入力stem>/` が存在するモデルは処理済みとしてスキップ
- 同じ stem の別拡張子が共存する場合は出力衝突として停止
- `input/` と `output/` が存在しない場合は起動時に作成

保存中は非ドット一時フォルダを使います。

```text
output/<stem>.__working__/
```

全出力が正常に完了してから：

```text
output/<stem>/
```

へ rename します。これは macOS でドット始まり一時フォルダの hidden 属性が rename 後にも残る事例を避けるためです。

## 4. Mesh QA・Normal・外観

読込時にメッシュ情報を確認し、Normal が不足する場合は表示・処理に必要な Normal を計算します。

基本方針：

- 入力メッシュの頂点密度・面数を勝手に削減しない
- 自動 decimation を行わない
- texture / vertex color があれば利用可能
- non-watertight mesh に対して「外向き Normal が保証された」とは扱わない

## 5. 正規化後モデル

入力形式にかかわらず、正規化後モデルは PLY で保存します。

```text
<stem>_rev.ply
```

---

<a id="pottery"></a>
# 土器版

[ページ先頭へ戻る](#artifact-pose-normalizer) / [石器版へ](#lithic)

## 1. 土器の基本ワークフロー

1. モデルを読込
2. `モデル種別 = 土器`
3. 入力単位と Mesh QA を確認
4. Slice / Rim / Base / Manual で姿勢を決定
5. Z 軸回転で正面を決定
6. オルソ面・表現・特殊図・出力形式を設定
7. 必要に応じてオルソ画像プレビューを確認
8. `計測一覧出力`
9. `保存して次へ`

## 2. 姿勢決定

水平・傾きの決定方法：

- `Slice`
- `Rim`
- `Base`
- `Manual (3 points)`

基本方針：

- Slice は中心軸から姿勢 Z を決定
- Rim / Base / Manual は基準面で傾きを固定
- Rim / Base / Manual 後の Slice は姿勢を再回転せず、固定姿勢内で中心軸位置を求める
- `orientation_z_axis` と `center_axis` は別概念として扱う
- 原点は中心軸と姿勢決定後 AABB 下底面 `z_min` の交点
- 正面は最後に Z 軸回転のみで手動決定

Transform 規約：

```text
p_normalized = M_raw_to_normalized @ [x, y, z, 1]^T
```

## 3. 土器メイン3D表示

表示方向：

- `Ortho Front`
- `Oblique`

平行投影を使用します。

表示機能：

- Texture / vertex color ON/OFF
- Normal shading ON/OFF
- 20 / 50 / 100 mm の表示スケール
- Zoom 25–400%
- `- / 100% / +` とスライダー
- ホイール Zoom に追従
- 中心軸を紫色補助線で表示
- PyVista の不要な `Distance` scalar bar は表示しない

## 4. 土器オルソ面

選択可能：

```text
Front
Back
Left
Right
Top
Bottom
```

基本6面配置：

```text
              TOP
LEFT        FRONT        RIGHT        BACK
            BOTTOM
```

すべて同じ orthographic scale を使用します。

土器 Front カメラ規約：

- camera side: `-Y`
- looking toward: `+Y`
- up: `+Z`

## 5. 土器オルソ表現

基本表現：

1. `テクスチャ / 頂点カラー`
2. `テクスチャ / 頂点カラー + Normal`
3. `Normalのみ（シェード）`

特殊図：

- `縦断面`
- `半截`
- `1/4半截`

### 縦断面

姿勢・位置決定後 AABB の x-y 中点を通る垂直軸を基準に、

```text
y = (y_min + y_max) / 2
```

の x-z 平面で作成します。

v0.4.2 では断面線と断面塗りの処理を分離しています。`vtkCutter` / `vtkStripper` が返した断面 path は、線画・SVGでは **open / closed をそのまま保持**します。open path の始点と終点を無条件に直線で結ぶ処理は行わないため、欠損や非 watertight 部分で長い人工的な斜線が生成されることを防ぎます。

### 半截

Front 側半分を除去した状態を正面から表示し、切断面を黒で示します。独立PNGではなく複合画像内へ配置します。

黒い切断面の fill は、線画用 path を強制的に閉じるのではなく、fill 専用に次の順で再構成します。

```text
Cutter / Stripper の断面 path
        ↓
端点の近接 snap
        ↓
小さい gap + 接線方向が連続する path のみ stitch
        ↓
閉輪郭を even-odd rule で fill
        ↓
残った微小 gap は限定的な raster closing
        ↓
切断面を黒 fill
```

このため、断面線そのものには補完線を描かず、小さなメッシュ切れによる fill 欠落だけを補います。大きな gap は自動的に接続しません。

複数の閉輪郭が入れ子になる場合は even-odd rule で塗りを反転するため、内側領域を一律に黒く塗り潰さないようにしています。

### 1/4半截

- 左半分：通常 Front
- 右半分：半截状態

半截・1/4半截の黒い切断面には、上記の fill 専用断面再構成を共通して使用します。石器の断面抽出・配置ロジックはこの v0.4.2 修正の対象外です。

### 複合配置例

```text
Front輪郭 | Left | Front | 1/4半截 | 半截 | Right | Back | 縦断面
```

Top / Bottom は Front と同じ横位置の上下に配置します。

## 6. 土器輪郭・SVG

出力形式：

```text
PNGのみ
SVG
PNG+輪郭（SVG由来）
```

PNG+輪郭の重ね描き対象：

- Front
- Back
- Left
- Right
- Top
- Bottom

対象外：

- Front輪郭独立パネル
- 縦断面
- 半截
- 1/4半截

PNG輪郭線幅：

```text
1 px
2 px
3 px
5 px
```

複合SVG：

```text
<stem>_ortho_outline.svg
```

縦断面が選択されている場合はSVGにも含めます。半截・1/4半截は raster rendering を含むためSVGには含めません。

## 7. 土器の個別出力

`各面を個別ファイルでも出力` が ON の場合、選択した各面の PNG / SVG、Front輪郭、section を個別出力します。

半截・1/4半截は複合画像内の要素として扱います。

## 8. 土器ティック

面間隔のデフォルト：

```text
10 mm
```

Front 中軸線ティック、Top 半截ラインティックの仕様：

- 線幅：`5 px`
- モデル外縁からの空き：面間隔の `1/4`
- ティック長：面間隔の `1/2`
- 外側残り：面間隔の `1/4`

面間隔 10 mm の場合：

```text
2.5 mm gap + 5 mm tick + 2.5 mm
```

## 9. 土器オルソプレビュー

`オルソ画像プレビューを開く` で別ウインドウを開きます。

保存用PNGと同じ配置ロジックを使用し、以下の変更に追従します。

- 6面選択
- Texture / Texture+Normal / Shade
- 縦断面 / 半截 / 1/4半截
- PNG / PNG+輪郭
- 面間隔
- スケールバー
- 輪郭線幅

初期表示は `Fit width`。

Mac：

- トラックパッド pinch → Zoom
- 2本指スクロール → Scroll

マウス：

- `Ctrl + wheel` → Zoom
- wheel → Scroll

---

<a id="lithic"></a>
# 石器版

[ページ先頭へ戻る](#artifact-pose-normalizer) / [土器版へ](#pottery)

## 1. 石器の基本ワークフロー

1. モデルを読込
2. `モデル種別 = 石器` を選択
3. `oriented_bounds()` による自動初期姿勢推定を実行
4. 中央 X-Z 断面による Y 軸自動補正を実行
5. Front / Right / Bottom の3面表示で確認
6. 必要に応じて Y / X / Z 軸回転を手動調整
7. `姿勢決定`
8. final bbox 左下隅を原点 `(0,0,0)` に設定
9. オルソ・輪郭・断面設定
10. `プレビュー確認`
11. 青い断面線を必要に応じて移動・追加・削除
12. 再度 `プレビュー確認` で断面を再生成
13. `計測一覧出力`
14. `保存して次へ`

`姿勢決定` 後も `石器姿勢に戻る` で姿勢調整画面へ戻り、再調整後に再度決定できます。

## 2. 石器の自動初期姿勢推定

石器を選択すると、まず Trimesh の minimum-volume oriented bounding box を適用します。

```python
trimesh.bounds.oriented_bounds(
    mesh,
    angle_digits=1,
    ordered=False,
)
```

OBB の3軸を寸法順に解釈して、石器座標系を：

```text
X = 幅
Y = 長さ（最大長軸）
Z = 厚さ
```

に割り当てます。

### 中央 X-Z 断面による追加補正

OBB 適用後、OBB 中心の：

```text
y = 0
```

における X-Z 断面を取得します。

断面は大規模メッシュでも扱いやすいよう、三角形と平面の交点をチャンク処理で直接計算します。

左右端の単一頂点だけには依存せず、外側 2% の候補領域から代表 Z を求め、左右端を結ぶ線の傾斜を評価します。その線が X 軸と平行になるよう **Y 軸回転**で自動補正します。

したがって石器の自動姿勢は：

```text
original
  ↓
minimum-volume OBB
  ↓
X=幅 / Y=長さ / Z=厚さ
  ↓
中央 X-Z 断面
  ↓
Y軸自動水平化
  ↓
automatic lithic pose
```

となります。

## 3. 石器モデルビュー

自動姿勢推定後、右側メイン画面に：

```text
Front (X-Y)
Right (Y-Z)
Bottom (X-Z)
```

を表示します。

**デフォルト表示は陰影図（Shade）**です。

## 4. 石器の手動回転

左パネルの回転ギズモは：

```text
Y
X
Z
```

の順です。

意味：

```text
Y = 長さ
X = 幅
Z = 厚さ
```

各軸に：

- `-90°`
- `0°`
- `+90°`
- ダイヤル
- 数値入力

を備えます。

手動回転は自動姿勢推定後の姿勢に対する追加回転です。

## 5. 石器の姿勢決定と原点

`姿勢決定` を押した時点で現在の姿勢を確定します。

確定後、最終姿勢の axis-aligned bounding box の最小隅：

```text
(Xmin, Ymin, Zmin)
```

が：

```text
(0, 0, 0)
```

になるよう座標原点を設定します。

その後も `石器姿勢に戻る` で調整画面へ戻れます。

## 6. 石器 Transformation Matrix

石器では Transform を段階別に保持します。

### original → OBB

常に保存：

```text
transform_original_to_obb.csv
transform_original_to_obb_cloudcompare.txt
```

### OBB → result

OBB 後に自動補正、手動回転、原点移動等があり、OBB→result が恒等変換でない場合に保存：

```text
transform_obb_to_result.csv
transform_obb_to_result_cloudcompare.txt
```

OBB のみが最終結果であり、OBB→result が恒等変換の場合は第2 matrix を出力しません。

最終合成変換は `transform.json` に保存します。

```text
p_result = M_obb_to_result @ M_original_to_obb @ [x,y,z,1]^T
```

## 7. 石器出力パネル

石器の基本出力は土器版と同様です。

選択可能な投影面：

```text
Front
Back
Left
Right
Top
Bottom
```

基本6面配置：

```text
              TOP
LEFT        FRONT        RIGHT        BACK
            BOTTOM
```

表現：

1. `テクスチャ / 頂点カラー`
2. `テクスチャ / 頂点カラー + Normal`
3. `Normalのみ（シェード）`

出力形式：

```text
PNGのみ
SVG
PNG+輪郭（SVG由来）
```

輪郭線幅：

```text
1 px
2 px
3 px
5 px
```

石器版には：

- 半截
- 1/4半截

はありません。

## 8. 石器プレビュー

`プレビュー確認` を押すと、**別ウインドウを開かず、右側メイン画面を展開図ビューへ切り替えます。**

プレビューの基本モデル表示は **Shade** です。Shade を出力パネルで OFF にした場合は、選択されている別の表現を使用します。

出力面設定を変更した場合は、再度 `プレビュー確認` を押して表示を更新します。

## 9. 石器断面設定

プレビュー画面には青い断面位置線を表示します。

青線はモデル輪郭内だけでなく、**プレビュー画面全体に連続**して表示します。

青線は位置設定用であり、保存されるオルソ画像には描画しません。保存画像には断面位置を示すティックを描画します。

### 初期断面

初期状態では中央位置に2断面を設定します。

#### 断面（X）

X 方向に沿う X-Z 断面：

```text
y = constant
```

プレビューでは横方向の青線として表示します。

#### 断面（Y）

Y 方向に沿う Y-Z 断面：

```text
x = constant
```

Front / Back に対応する2本の縦青線として表示し、一方を移動すると他方も連動します。

### 断面線の操作

- 青線をクリックして選択
- ドラッグして移動
- `断面追加（X）`
- `断面追加（Y）`
- `削除`

ライン選択は描画順ではなく、クリック位置から最も近い断面線を View 側で判定します。

新規追加した同方向断面は完全重複を避けるため、中央から交互にずらして配置します。

```text
60%, 40%, 70%, 30%, 80%, 20% ...
```

青線を移動した後、`プレビュー確認` を押すと対応する断面を再生成します。

## 10. 石器断面の配置

### X-Z 断面

`Bottom` が選択されている場合：

```text
Bottom の下
```

に配置します。

`Bottom` が選択されていない場合：

```text
Front の下
```

に配置します。

複数の X-Z 断面は下方向に配置します。ただし順序は断面線の追加・描画順ではなく、**Front 上での位置が上→下となる順**です。最も上側の横断面が先頭、その下側の断面が順に続きます。

### Y-Z 断面

展開図の最右端に配置します。

6面をすべて表示している場合：

```text
Back の右
```

になります。

複数の Y-Z 断面の順序も断面線の追加・描画順ではなく、**Back 上での位置が左→右となる順**です。Back は左右反転表示なので、内部の正規化位置値では大きい値から小さい値へ並びます。

## 11. 石器断面位置ティック

断面位置は、保存される複合画像に黒いティックで表示します。

仕様は土器版と同じです。面間隔を `S` とすると：

- モデル外縁からの空き：`S / 4`
- ティック長：`S / 2`
- 外側残り：`S / 4`
- 線幅：`5 px`

### Y-Z断面のティック

`x = constant` の位置を：

- Front 上下
- Back 上下

に縦ティックで表示します。

### X-Z断面のティック

`y = constant` の位置を：

- Front 左右
- Back 左右
- Left 左右
- Right 左右

に横ティックで表示します。

## 12. 石器の個別出力

`各面・断面を個別ファイルでも出力` が ON の場合：

- 選択した各面の PNG
- 選択した各面の SVG 輪郭
- X-Z / Y-Z の断面 PNG
- X-Z / Y-Z の断面 SVG

を条件に応じて追加出力します。

---


---

<a id="measurements"></a>
# 計測データ CSV

[ページ先頭へ戻る](#artifact-pose-normalizer) / [土器版へ](#pottery) / [石器版へ](#lithic)

v0.4.0 から、正規化後の座標系に基づく計測値を CSV で出力します。

## 1. 個別資料ごとの計測 CSV

`保存して次へ` を実行すると、各資料の出力フォルダに必ず1つの計測 CSV を作成します。

```text
output/<stem>/<stem>_measurements.csv
```

### 土器・石器共通

最終姿勢の axis-aligned bounding box について：

```text
bbox_x
bbox_y
bbox_z
```

を記録します。

入力単位での値に加えて、一覧利用しやすいよう mm 換算値も記録します。

```text
bbox_x_mm
bbox_y_mm
bbox_z_mm
```

### 石器のみ：断面 bbox

同じ `<stem>_measurements.csv` に、設定された各断面を1行ずつ追加します。

現在の断面定義は：

```text
断面（X） = X-Z 断面 / y = constant
断面（Y） = Y-Z 断面 / x = constant
```

です。

したがって各断面では実際の断面平面に対応して：

```text
X-Z断面 → bbox_x, bbox_z
Y-Z断面 → bbox_y, bbox_z
```

を記録し、断面に垂直な軸の値は空欄とします。

あわせて：

```text
record_id
section_plane
section_position
section_coordinate
status
```

を記録します。

断面がモデルと交差しない場合は、寸法を空欄として：

```text
status = no_intersection
```

を記録します。

## 2. 計測一覧出力

土器・石器それぞれの出力パネルでは、作業順を：

```text
プレビュー確認
↓
計測一覧出力
↓
保存して次へ
```

としています。

`計測一覧出力` ボタンは `保存して次へ` の直上に配置しています。

また、現在資料の一覧が未出力、または姿勢・正面・単位の変更後に一覧が再出力されていない場合、`保存して次へ` は実行できません。

1回の `計測一覧出力` で、以下の **2種類の inventory** を同時に更新します。

### 2-1. 資料のジオメトリ代表値一覧

土器：

```text
output/inventory-pottery.csv
```

石器：

```text
output/inventory-lithic.csv
```

列は代表値だけに限定します。

```text
source_stem
bbox_x_mm
bbox_y_mm
bbox_z_mm
```

同じ `source_stem` がすでに存在する場合はその行を更新し、重複行は作りません。

### 2-2. 3Dモデル・データ一覧

土器：

```text
output/inventory-model-pottery.csv
```

石器：

```text
output/inventory-model-lithic.csv
```

列：

```text
source_file
source_stem
source_sha256
mesh_count
file_size_bytes
file_size_mb
surface_area_mm2
volume_mm3
is_watertight
volume_status
```

`mesh_count` は、Trimesh 読み込み後の三角形 face 数です。

`file_size_bytes` / `file_size_mb` は **元の3Dメッシュファイル単体**のサイズです。OBJ の場合は `.obj` ファイルだけを対象とし、MTL や JPEG/PNG テクスチャは合算しません。

`surface_area_mm2` は元メッシュの表面積を入力単位から mm² へ換算した値です。回転・平行移動では表面積が変わらないため、正規化前後で同じ値です。

`volume_mm3` は Trimesh の mesh volume の絶対値を mm³ に換算して記録します。閉じたメッシュでは体積値として利用できます。非 watertight メッシュでも Trimesh は値を返す場合があるため、その場合は：

```text
is_watertight = False
volume_status = non_watertight_estimate
```

として、閉合メッシュの実体積と区別します。

同一3Dモデルの更新判定には `source_sha256` を使用します。

CSV は初回実行時に自動作成され、UTF-8 BOM 付きで保存されます。


<a id="outputs"></a>
# 出力ファイルと Transform

## 1. 共通出力フォルダ

入力：

```text
input/sample.obj
```

の場合：

```text
output/sample/
```

へ出力します。

## 2. 土器の主な出力例

```text
output/pot001/
├── pot001_rev.ply
├── transform.json
├── transform_matrix.csv
├── transform_matrix_cloudcompare.txt
├── pot001_ortho_texture.png
├── pot001_ortho_texture_normal.png
├── pot001_ortho_shade.png
├── pot001_ortho_texture_outline.png
├── pot001_ortho_texture_normal_outline.png
├── pot001_ortho_shade_outline.png
└── pot001_ortho_outline.svg
```

実際のファイル数は選択した面・表現・特殊図・出力形式によって変わります。

## 3. 石器の主な出力例

```text
output/lithic001/
├── lithic001_rev.ply
├── transform.json
├── transform_original_to_obb.csv
├── transform_original_to_obb_cloudcompare.txt
├── transform_obb_to_result.csv                  # 必要な場合のみ
├── transform_obb_to_result_cloudcompare.txt     # 必要な場合のみ
├── lithic001_ortho_texture.png
├── lithic001_ortho_texture_normal.png
├── lithic001_ortho_shade.png
├── lithic001_ortho_*_outline.png                # PNG+輪郭 ON時
└── lithic001_ortho_outline.svg                  # SVG ON時
```

個別出力 ON の場合は各投影面と各断面の PNG / SVG が追加されます。

## 4. Scale bar

オルソ出力：

```text
20 mm
50 mm
100 mm
```

デフォルト：

```text
50 mm
```

## 5. 大規模メッシュ

本アプリはモデル品質を自動的に低下させません。

実用上の目安：

- 約70万～100万 faces：通常運用しやすい範囲
- 数百万 faces：OBB・断面計算自体は可能だが、複数オルソ・輪郭・高解像度レンダリング時のメモリと処理時間に注意

石器の中央断面による自動補正では、三角形―平面交差をチャンク処理し、大規模メッシュでのメモリ負荷を抑えています。

---

<a id="environment"></a>
# Python 環境・実行方法

## 1. 推奨フォルダ構成

```text
ArtifactPoseNormalizer/
├── app.py
├── pose_core.py
├── check_environment.py
├── self_test.py
├── requirements.txt
├── README.md
├── docs/
│   └── macos_qt_venv_issue.md
├── input/
└── output/
```

`pose_core.py` は **pip でインストールするライブラリではなく、このアプリに含まれる必須ファイル**です。`app.py` と同じフォルダに置いてください。

`input/` と `output/` は存在しない場合、アプリ起動時に作成されます。

## 2. requirements.txt の確認結果

v0.4.2 の `app.py` と `pose_core.py` の import を再確認し、アプリが直接利用する第三者パッケージを `requirements.txt` に明示しました。

```text
numpy==2.5.2
scipy==1.18.0
trimesh==5.0.0
pyvista==0.48.4
pyvistaqt==0.12.0
vtk==9.6.2
PySide6==6.10.3
QtPy==2.4.3
Pillow==12.3.0
```

用途：

| パッケージ | 主な用途 |
|---|---|
| NumPy | 座標・行列・配列計算 |
| SciPy | 石器 OBB の凸包計算、土器断面 fill の画像処理 |
| Trimesh | OBJ / PLY / GLB 読込、OBB、メッシュ計測 |
| PyVista | 3D表示、オルソレンダリング、VTK操作 |
| PyVistaQt | PyVista の Qt GUI 埋め込み |
| VTK | 3D描画、断面 Cutter / Stripper、輪郭処理 |
| PySide6 | GUI |
| QtPy | PyVistaQt が利用する Qt 抽象化レイヤ |
| Pillow | PNG画像、輪郭・断面・スケール描画 |

Python 標準ライブラリ（`csv`, `json`, `math`, `pathlib`, `tempfile`, `xml` など）は Python 本体に含まれるため `requirements.txt` には記載しません。

また、上記パッケージ自身が必要とする内部依存パッケージは `pip` が自動的に導入します。**初心者の方が個別にモジュールを1つずつインストールする必要はありません。**

**SciPy は必須です。** 石器の `trimesh.bounds.oriented_bounds()` に加えて、v0.4.2 の土器断面 fill repair でも `scipy.ndimage` を使用します。

## 3. 最初に確認すること

Python 3.13 系を推奨します。

macOS：

```bash
python3.13 --version
```

Windows PowerShell：

```powershell
python --version
```

`Python 3.13.x` と表示されれば、以下の標準手順を使用できます。

## 4. macOS：初回セットアップ

ターミナルでプロジェクトフォルダへ移動します。

```bash
cd /path/to/ArtifactPoseNormalizer
```

仮想環境 `venv` を作成・有効化します。

```bash
python3.13 -m venv venv
source venv/bin/activate
```

pip 関係を更新してから、**requirements.txt を1回インストールするだけで必要な外部パッケージをまとめて導入できます。**

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

依存関係の整合性を確認します。

```bash
python -m pip check
python check_environment.py
```

最後に起動します。

```bash
python app.py
```

### macOS の Qt 起動エラー

本プロジェクトの検証では、`.venv` という名前の環境で Qt platform plugin の file flags に関する問題が発生した例があるため、通常手順では仮想環境名を **`venv`** に統一しています。`.venv` が一般に使用不能という意味ではありません。

詳細：

```text
docs/macos_qt_venv_issue.md
```

最小 Qt 起動確認だけを行う場合：

```bash
python -c 'from PySide6.QtWidgets import QApplication; app=QApplication([]); print("QApplication OK"); app.quit()'
```

## 5. Windows / PowerShell：初回セットアップ

PowerShell でプロジェクトフォルダへ移動します。

```powershell
cd C:\path\to\ArtifactPoseNormalizer
```

仮想環境を作成します。

```powershell
python -m venv venv
```

有効化します。

```powershell
.\venv\Scripts\Activate.ps1
```

`running scripts is disabled on this system` と表示された場合だけ、現在の PowerShell セッションについて実行を許可してから再度有効化します。

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

必要な外部パッケージをまとめて導入します。

```powershell
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

確認：

```powershell
python -m pip check
python check_environment.py
```

起動：

```powershell
python app.py
```

## 6. `check_environment.py`

初心者向けの依存関係確認スクリプトです。

```bash
python check_environment.py
```

次を順番に確認します。

- NumPy
- SciPy
- Trimesh
- PyVista
- PyVistaQt
- VTK
- PySide6
- QtPy
- Pillow
- ローカル `pose_core.py`
- Qt `QApplication` / platform plugin

正常な場合、最後に：

```text
ENVIRONMENT CHECK PASSED
```

と表示します。

## 7. よくあるエラー

### `ModuleNotFoundError: No module named '...'`

まず仮想環境が有効か確認します。

macOS：

```bash
which python
```

`.../ArtifactPoseNormalizer/venv/bin/python` のように表示されるのが正常です。

Windows PowerShell：

```powershell
Get-Command python
```

`...\ArtifactPoseNormalizer\venv\Scripts\python.exe` を指していることを確認します。

その後：

```bash
python -m pip install -r requirements.txt
python -m pip check
python check_environment.py
```

を再実行してください。

### `No module named 'pose_core'`

`pose_core.py` は pip パッケージではありません。

```text
app.py
pose_core.py
```

が同じフォルダにあることを確認してください。

### `No module named 'scipy'`

v0.4.2 では SciPy は任意ではなく必須です。

```bash
python -m pip install -r requirements.txt
```

を実行してください。SciPy だけを個別に追加する必要はありません。

### Qt platform plugin エラー

まず：

```bash
python check_environment.py
```

で Qt の段階だけが失敗しているか確認してください。macOS では `docs/macos_qt_venv_issue.md` も参照してください。

## 8. SELF TEST

共通計算コアの簡易テスト：

```bash
python self_test.py
```

正常終了時：

```text
SELF TEST PASSED
```

`self_test.py` は主として姿勢・Normal・メッシュ計算を確認します。土器・石器の GUI 操作、3Dビュー、インタラクティブ断面線、オルソ配置は `app.py` を起動して確認してください。

## 9. 更新時の推奨手順

`requirements.txt` が変更された場合は、既存 `venv` 内で：

```bash
python -m pip install -r requirements.txt
python -m pip check
python check_environment.py
```

を実行してください。

環境が大きく崩れた場合は、個別モジュールを継ぎ足すより `venv` を作り直し、`requirements.txt` から再構築する方が再現性があります。

---

# 開発ファイルについて

正式利用では：

```text
app.py
```

を使用します。

`app_v0_1_xx.py`、`app_v0_2_x.py`、`app_v0_3_x.py` は開発・検証履歴として扱い、通常運用の起動ファイルにはしません。
