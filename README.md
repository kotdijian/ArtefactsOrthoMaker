# Artifact Pose Normalizer — 土器版

OBJ / PLY / GLB 形式の土器3Dモデルを読み込み、姿勢・座標系を正規化し、正規化モデル、変換行列、オルソ画像、輪郭線、縦断面・半截図をまとめて作成する Python GUI アプリです。

この `app.py` は、v0.1.x 系列で開発・検証した機能を収束した土器版です。  
内部の `APP_VERSION` は開発系列の最終番号 `0.1.13` を保持しています。以後、通常利用では `app_v0_1_xx.py` ではなく **`app.py`** を使用してください。

---

## 1. 主な機能

### 入力・キュー

- `input/` 内の `.obj / .ply / .glb` をファイル名昇順で処理
- `output/<入力stem>/` が存在するファイルは処理済みとしてスキップ
- 同じ stem の別拡張子が共存する場合は出力衝突として停止
- 入力単位 `mm / cm / m` を指定
- 頂点座標値そのものは変更せず、mm換算だけに単位設定を使用
- Normal を検証し、必要に応じて計算
- OBJ texture / PLY vertex color / GLB appearance を可能な範囲で利用

### 姿勢・原点・正面

水平・傾きの決定方法：

- `Slice`
- `Rim`
- `Base`
- `Manual (3 points)`

基本方針：

- Slice は中心軸から姿勢を決定
- Rim / Base / Manual は基準面で傾きを固定
- その後 Slice を再実行して中心軸位置を求める
- `orientation_z_axis` と `center_axis` は別概念として扱う
- 原点は、中心軸と姿勢決定後 AABB の下底面 `z_min` の交点
- 正面は最後に Z 軸回転だけで手動決定

### メイン3D表示

表示方向：

- `Ortho Front`
- `Oblique`

どちらも平行投影です。

表示機能：

- Texture / vertex color ON/OFF
- Normal shading ON/OFF
- 20 / 50 / 100 mm の実寸表示スケール
- Zoom 25–400%
- `- / 100% / +` とスライダー
- マウスホイールによるカメラZoomにも追従
- 中心軸は紫色の補助線として表示
- PyVista の `Distance` スカラー・カラーバーは表示しない

---

## 2. 対応形式

### 入力

```text
.obj
.ply
.glb
```

STL は対象外です。

### 正規化後モデル

**入力形式にかかわらず PLY で保存します。**

```text
<input-stem>_rev.ply
```

例：

```text
pot001.obj → pot001_rev.ply
pot002.glb → pot002_rev.ply
pot003.ply → pot003_rev.ply
```

座標値は入力単位のままです。単位指定によってモデル座標を1000倍・1/1000倍する処理は行いません。

---

## 3. 推奨フォルダ構成

```text
ArtifactPoseNormalizer_Pottery/
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

`input/` と `output/` は、存在しない場合は起動時に作成されます。

---

## 4. 処理済み判定と一時出力

処理済み判定：

```text
output/<入力stem>/
```

が存在すれば処理済みです。

保存中は macOS の hidden 属性問題を避けるため、ドットで始まらない一時ディレクトリを使います。

```text
output/<stem>.__working__/
```

モデル、Transform、PNG / SVG がすべて正常に出力された後、

```text
output/<stem>/
```

へ rename します。

再処理したい場合は該当する最終出力フォルダを削除し、GUI の `inputフォルダを再読込` を押してください。

---

## 5. Python環境

検証環境：

```text
Python 3.13.7
numpy 2.5.2
trimesh 5.0.0
pyvista 0.48.4
pyvistaqt 0.12.0
vtk 9.6.2
PySide6 6.10.3
Pillow 12.3.0
```

依存関係は `requirements.txt` に固定しています。

### macOS

```bash
cd /path/to/ArtifactPoseNormalizer_Pottery
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

### Windows / PowerShell

```powershell
cd C:\path\to\ArtifactPoseNormalizer_Pottery
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python app.py
```

PowerShell の ExecutionPolicy で activation が拒否される場合は、現在のセッションだけ許可します。

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

---

## 6. SELF TEST

計算コアの確認：

```bash
python self_test.py
```

正常終了時：

```text
SELF TEST PASSED
```

`self_test.py` は姿勢推定・Normal処理・メッシュ入出力など計算コアを確認します。GUI のプレビューや複合オルソ配置そのものは GUI 実行で確認してください。

---

## 7. 基本ワークフロー

1. `input/` にモデルを配置
2. `python app.py`
3. 入力単位を確認
4. Mesh QA を確認
5. Slice / Rim / Base / Manual で姿勢を決定
6. Z回転で正面を決定
7. オルソ面・表現・特殊図・出力形式を選択
8. 必要に応じてオルソプレビューを確認
9. `保存して次へ`
10. 次の未処理モデルへ進む

---

## 8. 入力単位

GUI：

```text
入力単位 [ mm / cm / m ]
```

これは **物理量としての mm 換算**に使います。

影響する主な項目：

- 展開図の面間隔
- 表示・出力スケールバー
- SVG の物理座標
- ティック長

例：モデル座標 `1.0` が 1 m を意味するデータなら `m` を選択します。  
座標値 `1.0` を `1000.0` に書き換える処理は行いません。

入力単位を誤ると、オルソPNGの計算寸法が異常に大きくなる場合があります。

---

## 9. オルソ面

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

すべての面は同じ orthographic scale を使用します。

Front カメラ規約：

- camera side: `-Y`
- looking toward: `+Y`
- up: `+Z`

---

## 10. オルソ表現

基本表現：

1. `テクスチャ / 頂点カラー`
2. `テクスチャ / 頂点カラー + Normal`
3. `Normalのみ（シェード）`

外観情報がないモデルでは、基本的に `Normalのみ（シェード）` を使用します。

特殊図：

- `縦断面`
- `半截`
- `1/4半截`

---

## 11. 縦断面・半截・1/4半截

### 基準軸

特殊図でいう中軸は、**姿勢・位置決定後 AABB の x-y 中点を通る垂直軸**です。

縦断面は、その軸を通る x-z 平面：

```text
y = (y_min + y_max) / 2
```

で作成します。

### 縦断面

- x-z 断面線を表示
- 選択時は複合PNGの右端へ配置
- SVG が ON の場合は複合SVGにも含める
- `各面を個別ファイルでも出力` が ON の場合だけ単独 section PNG / SVG を出力

### 半截

Front 側半分を除去した状態を正面から表示し、切断面を黒で示します。

**単独半截PNGは出力しません。**  
複合オルソ画像内で Front の直後へ配置します。

### 1/4半截

- 左半分：通常 Front
- 右半分：半截状態

複合配置では Front の直後に入ります。

### 複合横方向の例

6面＋1/4半截＋半截＋縦断面：

```text
Front輪郭 | Left | Front | 1/4半截 | 半截 | Right | Back | 縦断面
```

1/4半截 OFF、半截 ON：

```text
Front輪郭 | Left | Front | 半截 | Right | Back | 縦断面
```

Front のみ＋縦断面：

```text
Front輪郭 | Front | 縦断面
```

Top / Bottom は Front と同じ横位置の上下に配置されます。

---

## 12. Front輪郭と輪郭重ね描き

複合オルソPNGには、**Front輪郭を左端の独立パネルとして配置**します。

出力形式：

```text
PNGのみ
SVG
PNG+輪郭（SVG由来）
```

`PNG+輪郭` の輪郭重ね描き対象は、通常のオルソ面だけです。

対象：

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

---

## 13. SVG

SVG は投影輪郭線をベクターとして保存します。

複合SVG：

```text
<stem>_ortho_outline.svg
```

縦断面が選択されている場合は、複合SVGの右端にも縦断面を含めます。

半截と1/4半截は raster rendering を含むため、SVGには埋め込みません。

---

## 14. 個別出力

`各面を個別ファイルでも出力` が OFF の場合：

- 複合PNG / SVGだけを出力
- Front輪郭単独ファイルを出さない
- section単独ファイルを出さない

ON の場合：

- 選択した各面の個別PNG
- 必要な個別SVG輪郭
- `front_outline.png`
- `front_outline.svg`（SVG ON時）
- `section.png`（縦断面 ON + PNG系 ON時）
- `section.svg`（縦断面 ON + SVG ON時）

を出力します。

半截・1/4半截は独立画像ではなく複合画像内の要素として扱います。

---

## 15. 展開図間隔とティック

面間隔のデフォルト：

```text
10 mm
```

### Front 中軸線ティック

Front の上下中央に表示します。

### Top 半截ラインティック

Top の左右中央に表示します。

両者の仕様：

- 太さ：`5 px`
- ティック長：面間隔の `1/2`
- モデル外縁からティックまでの余白：面間隔の `1/4`

面間隔 10 mm の場合：

```text
2.5 mm 余白 + 5 mm ティック + 2.5 mm
```

---

## 16. スケールバー

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

ラベル文字は v0.1.x 後期で大きくし、印刷・確認時の可読性を改善しています。

メイン3D表示左下のスケールも、平行投影の `parallel_scale` から実寸として計算します。

---

## 17. オルソ画像プレビュー

姿勢決定後、GUI の：

```text
オルソ画像プレビューを開く
```

で別ウインドウを開けます。

プレビューは保存用PNG生成処理と同じ配置ロジックを利用します。

### チェック状態への追従

プレビューウインドウが開いている状態で次を変更すると、自動更新します。

- Front / Back / Left / Right / Top / Bottom
- Texture
- Texture + Normal
- Shade
- 縦断面
- 半截
- 1/4半截
- PNGのみ
- PNG+輪郭
- 面間隔
- スケールバー
- PNG輪郭線幅

SVG はベクター出力なので、プレビューウインドウでは表示対象にせず PNG 系を表示します。

### 初期表示

画像はデフォルトで：

```text
Fit width
```

つまりプレビューウインドウ幅に合わせて表示します。

### Zoom操作

Macトラックパッド：

- ピンチ → Zoom
- 2本指スクロール → 通常スクロール

マウス：

- `Ctrl + ホイール` → Zoom
- 通常ホイール → スクロール

ボタン：

```text
-
100%
Fit width
+
```

Zoom範囲はプレビュー内部で 10–800% に制限しています。

---

## 18. 出力ファイル

例：入力が

```text
input/pot001.obj
```

の場合：

```text
output/pot001/
├── pot001_rev.ply
├── transform.json
├── transform_matrix.csv
├── transform_matrix_cloudcompare.txt
├── pot001_ortho_texture.png
├── pot001_ortho_texture_normal.png
├── pot001_ortho_shade.png
├── pot001_ortho_texture_outline.png          # PNG+輪郭 ON時
├── pot001_ortho_texture_normal_outline.png   # PNG+輪郭 ON時
├── pot001_ortho_shade_outline.png            # PNG+輪郭 ON時
└── pot001_ortho_outline.svg                  # SVG ON時
```

実際のファイル数は選択した表現・出力形式によって変化します。

個別出力 ON の場合は各面PNG / SVG、Front輪郭、section などが追加されます。

---

## 19. Transform

保存：

```text
transform.json
transform_matrix.csv
transform_matrix_cloudcompare.txt
```

変換規約：

```text
p_normalized = M_raw_to_normalized @ [x, y, z, 1]^T
```

`transform.json` には、入力単位、姿勢決定法、中心軸、正面回転、出力設定なども記録します。

---

## 20. 大規模メッシュ

本アプリは、解析・出力時にモデル品質を勝手に落とす設計にはしていません。

実用上の基準として：

- 約70万～100万 faces：通常運用の基準
- より高密度モデル：メモリ・オフスクリーン描画時間に注意

特に複数のオルソ表現、半截、1/4半截、輪郭抽出を同時に選ぶとレンダリング回数が増えます。

---

## 21. macOS Qt / PySide6 注意事項

本プロジェクトの検証中、特定の `.venv` 環境で PySide6 Qt plugin の `.dylib` に macOS の `UF_HIDDEN` が付与され、`cocoa` plugin を通常探索できなくなる現象を確認しました。

標準手順では：

```text
venv
```

を使用してください。

詳細は：

```text
docs/macos_qt_venv_issue.md
```

を参照してください。

---

## 22. 開発系列の扱い

開発中のファイル：

```text
app_v0_1_6.py
app_v0_1_7.py
...
app_v0_1_13.py
```

は履歴・検証用です。

**土器版の通常利用ファイルは `app.py` です。**

今後、新しい対象器種・機能を開発する場合も、土器版の安定版はこの `app.py` を基準として保持してください。
