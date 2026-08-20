# Artifact Pose Normalizer

OBJ / PLY / GLB 形式の考古資料3Dモデルを読み込み、**土器**または**石器**として姿勢・座標系を正規化し、正規化モデル、変換行列、オルソ画像、輪郭線、断面図を作成する Python GUI アプリです。

現在の正式実行ファイルは **`app.py`** です。v0.1.x 系で完成した土器機能と、v0.2–0.3 系で追加した石器機能を統合しています。`APP_VERSION` は `0.4.1` です。

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
8. `保存して次へ`

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

### 半截

Front 側半分を除去した状態を正面から表示し、切断面を黒で示します。独立PNGではなく複合画像内へ配置します。

### 1/4半截

- 左半分：通常 Front
- 右半分：半截状態

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
13. `保存して次へ`

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
├── self_test.py
├── requirements.txt
├── README.md
├── docs/
│   └── macos_qt_venv_issue.md
├── input/
└── output/
```

## 2. 検証・固定依存関係

```text
Python 3.13.x
numpy==2.5.2
scipy==1.18.0
trimesh==5.0.0
pyvista==0.48.4
pyvistaqt==0.12.0
vtk==9.6.2
PySide6==6.10.3
Pillow==12.3.0
```

**SciPy は石器の `trimesh.bounds.oriented_bounds()` に必要です。**

## 3. macOS

```bash
cd /path/to/ArtifactPoseNormalizer
python3.13 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

本プロジェクトの macOS 検証では `.venv` 環境で Qt platform plugin の file flags に関する問題を確認したため、README では `venv` を標準名にしています。一般論として `.venv` が使用不能という意味ではありません。

詳細：

```text
docs/macos_qt_venv_issue.md
```

## 4. Windows / PowerShell

```powershell
cd C:\path\to\ArtifactPoseNormalizer
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

ExecutionPolicy で activation が拒否される場合：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

## 5. SELF TEST

```bash
python self_test.py
```

正常終了時：

```text
SELF TEST PASSED
```

`self_test.py` は主として共通計算コアと従来の姿勢・Normal・メッシュ入出力を確認します。石器のGUI操作、3面ビュー、インタラクティブ断面線、展開図配置については `app.py` を起動して確認してください。

---

# 開発ファイルについて

正式利用では：

```text
app.py
```

を使用します。

`app_v0_1_xx.py`、`app_v0_2_x.py`、`app_v0_3_x.py` は開発・検証履歴として扱い、通常運用の起動ファイルにはしません。
