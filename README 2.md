# Artifact Pose Normalizer v0.1.4

OBJ / PLY / GLB 形式の土器・石器などの3Dモデルを読み込み、姿勢・座標系を正規化し、正規化モデル、変換行列、標準オルソ画像をまとめて保存するPython GUIアプリです。

v0.1.4では、毎回ファイル選択ダイアログを開く必要はありません。アプリフォルダ内の `input` にモデルを入れると、未処理ファイルをファイル名昇順で順番に読み込みます。

---

## 1. 主な機能

- `input` フォルダの OBJ / PLY / GLB をファイル名昇順で連続処理
- `output/<入力ファイル名>/` の存在を処理済み判定に使用
- 読み込み時に入力単位 `mm / cm / m` を指定
- 入力座標値そのものは拡大・縮小しない
- Normalを読み込み時に検証し、必要なら自動計算
- テクスチャ / 頂点カラーの有無を自動判定
- 3D表示を `Ortho Front / Oblique` で切替
- 3D表示パネル左下に20 / 50 / 100 mmの実寸スケールを表示
- 水平・傾きの決定方法
  - Slice
  - Rim
  - Base
  - Manual（3点）
- 姿勢確定後にSlice中心軸を求める
  - Sliceモードでは最初に得た中心軸を保持
  - Rim / Base / Manualでは水平決定後にSliceを再実行
- 中心軸と、姿勢決定後BBox下底面との交点をXYZ原点に設定
- 最後にZ軸回転だけを手動操作して「正面」を決定
- 姿勢決定後モデルを `<元ファイル名>_rev.<元と同じ形式>` で保存
- `transform.json` を保存
- raw → normalized の4×4変換行列をCSVで保存
- CloudCompare等で使いやすい空白区切り4×4行列も保存
- 選択した投影面を1枚に組み合わせたオルソPNGを出力
- 必要なら各面PNGも追加出力
- スケールバー 20 / 50 / 100 mm を選択可能（デフォルト50 mm）

---

# 2. 対応形式

## 入力

- `.obj`
- `.ply`
- `.glb`

STLは対象外です。

## 正規化後モデル

入力と同じファイル形式で保存します。

例：

```text
0001.obj → 0001_rev.obj
0002.ply → 0002_rev.ply
0003.glb → 0003_rev.glb
```

## オルソ画像

PNG固定です。

---

# 3. フォルダ構成

アプリフォルダは次の構成になります。

```text
ArtifactPoseNormalizer_v0.1.4/
├── app.py
├── pose_core.py
├── self_test.py
├── requirements.txt
├── README.md
├── input/
└── output/
```

`input` と `output` が無い場合は、アプリ起動時に自動作成されます。

入力例：

```text
input/
├── 0001.obj
├── 0002.glb
├── 0003.ply
└── 0004.obj
```

処理後：

```text
output/
├── 0001/
├── 0002/
├── 0003/
└── 0004/
```

---

# 4. ファイルの処理順

`input` 内の対応ファイルをファイル名の昇順で処理します。

たとえば：

```text
0001.obj
0002.obj
0003.glb
0010.ply
```

の順です。

数字だけのファイル名を使う場合は、

```text
0001
0002
0010
```

のように桁数を揃えることを推奨します。

`1.obj`, `2.obj`, `10.obj` のような名前では、文字列順のため意図した数字順と異なる場合があります。

---

# 5. 処理済み判定

処理済み判定は非常に単純です。

```text
output/<入力ファイル名>/
```

というフォルダが存在すれば、その入力ファイルは処理済みとしてスキップします。

例：

```text
input/0003.glb
output/0003/
```

が存在する場合、`0003.glb` は読み込みません。

## 再処理する場合

再処理したい個体の出力フォルダを削除します。

例：

```text
output/0003/
```

を削除して、GUIの

```text
inputフォルダを再読込
```

を押してください。

## 保存途中でエラーになった場合

v0.1.4では、保存中だけ

```text
output/.0003.__working__/
```

のような一時フォルダを使用します。

モデル、transform、オルソ画像のすべてが正常に出力された後で、最終的な

```text
output/0003/
```

へ名前を変更します。

したがって、保存途中の失敗で空の最終フォルダだけが残り、「処理済み」と誤判定されにくい構成です。

---

# 6. 同名ファイルについて

次のような入力は使用できません。

```text
input/sample.obj
input/sample.glb
```

どちらも出力先が

```text
output/sample/
```

になるためです。

この場合、起動時に警告します。どちらかの名前を変更してください。

---

# 7. Pythonの導入

## 推奨・検証環境

当面の標準検証環境は次のとおりです。

- **Python 3.13**
- macOS / Windows
- Apple Silicon Macを含む

Python 3.14はPySide6 / Qt周辺の環境差が大きいため、v0.1.xでは実験的扱いとします。
まずPython 3.13で動作確認してください。

Pythonは公式配布版を利用するのが簡単です。

Python公式：

```text
https://www.python.org/downloads/
```

---

# 8. macOSでのセットアップ

## 8-1. ターミナルを開く

macOSの「ターミナル」を起動します。

Python確認：

```bash
python3 --version
```

例：

```text
Python 3.13.x
```

## 8-2. アプリフォルダへ移動

たとえばDownloadsに展開した場合：

```bash
cd ~/Downloads/ArtifactPoseNormalizer_v0.1.4
```

分からない場合は、

1. `cd ` と入力
2. 半角スペースを入れる
3. Finderから `ArtifactPoseNormalizer_v0.1.4` フォルダをターミナルへドラッグ
4. Enter

でも構いません。

## 8-3. 仮想環境を作る

初回だけ実行します。

```bash
python3 -m venv .venv
```

## 8-4. 仮想環境を有効化

```bash
source .venv/bin/activate
```

成功するとターミナル行頭付近に

```text
(.venv)
```

と表示されます。

## 8-5. 必要モジュールを導入

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

# 9. Windowsでのセットアップ

PowerShellまたはコマンドプロンプトを使用します。

## 9-1. フォルダへ移動

例：

```powershell
cd C:\Users\ユーザー名\Downloads\ArtifactPoseNormalizer_v0.1.4
```

## 9-2. 仮想環境を作成

```powershell
python -m venv .venv
```

## 9-3. PowerShellで有効化

```powershell
.\.venv\Scripts\Activate.ps1
```

コマンドプロンプトの場合：

```cmd
.venv\Scripts\activate.bat
```

## 9-4. モジュールを導入

```powershell
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

---

# 10. SELF TEST

最初に計算部分のテストを推奨します。

```bash
python self_test.py
```

正常なら最後に：

```text
SELF TEST PASSED
```

と表示されます。

v0.1.4のSELF TESTは次を確認します。

1. 深い器形のSlice中心軸推定
2. 浅い器形のSlice中心軸推定
3. Normalを持たないPLYの読込・Normal自動計算
4. PLYの `_rev.ply` 再出力（TrimeshのNormal再計算を使わない）
5. GLB読込
6. GLBの `_rev.glb` 再出力

---

# 11. inputへモデルを入れる

起動前に、処理したいモデルを `input` へコピーします。

```text
input/
├── 0001.obj
├── 0002.ply
└── 0003.glb
```

OBJの場合、MTLやテクスチャ画像を使うモデルでは、OBJから参照できる位置関係を維持してください。

典型例：

```text
input/
├── 0001.obj
├── 0001.mtl
└── 0001_texture.jpg
```

アプリが処理対象として列挙するのは `.obj / .ply / .glb` だけです。MTLや画像はキューには入りません。

---

# 12. アプリ起動

仮想環境を有効にした状態で：

```bash
python app.py
```

起動すると `input` を自動走査し、未処理の先頭ファイルを読み込みます。

---

# 13. STEP 1：入力単位

GUI左上：

```text
1. 入力キュー / 単位

入力単位 [ mm ▼ ]
[inputフォルダを再読込]
```

選択肢：

```text
mm
cm
m
```

## 重要

この設定はモデルの頂点座標値を変更しません。

例えば座標値 `1.0` が1 mを意味するモデルで `m` を選んでも、頂点を1000倍にはしません。

単位設定は、主として：

- オルソ面間隔 10 mm
- スケールバー 20 / 50 / 100 mm

を入力モデル座標へ換算するために使用します。

## 読み込み後に単位を変更してもよい

v0.1.4では単位を変更してもメッシュを読み直す必要はありません。

例えば読み込み後に

```text
mm → m
```

へ変更すると、mm換算係数だけが更新されます。

---

# 14. Mesh QA

ファイル読み込み時に自動で確認します。

表示例：

```text
Vertices: 712,431
Faces: 1,421,005
Input unit: mm
Normals: source_present_validated
Appearance: vertex color
Watertight: False
```

## Normal

Normalの確認は姿勢決定時ではなく、ファイル読み込み時に行います。

- OBJ：`vn` の有無を確認
- PLY：`nx / ny / nz` の有無を確認
- GLB：GLB内部の `NORMAL` attributeを確認

その後、実際のメッシュ形状からNormalを計算し、計算可能かを検証します。

入力にNormalが無い場合も、表示・処理用Normalを自動計算します。

---

# 15. テクスチャ / 頂点カラー

表示欄：

```text
☑ テクスチャ / 頂点カラー
☑ Normalシェード
```

外観情報がある場合、必要に応じて表示をON/OFFできます。

## 外観情報がない場合

- テクスチャ画像を持たないOBJ
- 頂点カラーを持たないPLY
- 利用可能な外観情報を取得できないGLB

では、オルソ出力の

```text
Texture
Texture + Normal
```

は無効になり、

```text
Normalのみ（シェード）
```

だけが利用できます。

---


## モデル表示方向

v0.1.4では3D表示パネルの表示方向を切り替えられます。

```text
Ortho Front
Oblique
```

### Ortho Front

正面（Front）から見た平行投影です。

- 視線方向：`-Y → +Y`
- 上方向：`+Z`
- perspectiveによる遠近変形なし
- 正面決定時の確認に向く

### Oblique

斜め方向から見た平行投影です。

- 立体形状を確認しやすい3/4 view
- perspectiveではなくparallel projection
- 表示スケールを実寸として維持可能

表示方向を切り替えても、モデルの姿勢・座標・Transformは変化しません。
変更されるのはGUI上のカメラだけです。

## モデル表示パネルのスケール

3D表示パネル左下に実寸スケールを表示します。

選択肢：

```text
20 mm
50 mm
100 mm
```

デフォルト：

```text
50 mm
```

表示例：

```text
          50 mm
├────────────────────┤
```

- 黒線
- 両端に短い縦線
- 数値と単位は中央揃え
- 入力単位 `mm / cm / m` を考慮して実寸換算
- zoom後も更新


# 16. STEP 2：水平・傾き

選択肢：

```text
Slice
Rim
Base
Manual (3 points)
```

---

## 16-1. Slice

Sliceから器体中心軸を求め、その軸をZ軸へ合わせます。

```text
Slice中心軸
    ↓
Z軸へ整列
    ↓
中心軸をそのまま保持
```

深鉢・甕・壺のように高さが最大長軸になりやすい器形だけでなく、浅鉢・皿・椀・坏なども対象にするため、単純な最大長軸だけではなく複数Sliceの中心列を利用します。

---

## 16-2. Rim

口縁部候補を放射方向から抽出し、口縁が完全な平面でなくても代表的な水平面をrobust fittingします。

```text
口縁基準で水平決定
    ↓
その水平を固定
    ↓
Sliceで中心軸を再計算
```

後から中心軸をZへ再整列しません。

---

## 16-3. Base

底部・支持点候補から代表的な水平面を求めます。

底面が完全な平面でなくても、放射方向の支持点候補から最適化します。

```text
底面基準で水平決定
    ↓
水平を固定
    ↓
Sliceで中心軸を再計算
```

---

## 16-4. Manual（3点）

```text
[手動水平：3点を選択]
```

を押し、水平にしたい面上の3点を3Dビューでクリックします。

その3点から代表平面を作り、水平にします。

その後Slice中心軸を求めます。

---

# 17. Z上下反転

姿勢推定後、上下が逆だった場合：

```text
[Z上下反転]
```

を使用します。

---

# 18. 原点

このアプリでいう「接地面」は、実際の土器底面とは限りません。

姿勢決定後モデルのAxis-Aligned Bounding Boxの下底面：

```text
z = z_min
```

を仮想接地面と定義します。

原点は：

```text
Slice中心軸 × BBox下底面
```

の交点です。

この交点を

```text
X = 0
Y = 0
Z = 0
```

とします。

したがって平底、丸底、高台、尖底などを原点設定時に特別扱いしません。

---

# 19. STEP 3：正面

水平・傾きと原点が決まったあと、最後にZ軸回転だけを操作して「正面」を決めます。

## マウス操作

```text
左ドラッグ
```

モデルをZ軸まわりに回転します。

この操作ではZ軸方向や原点は変化しません。

## カメラを自由に動かす

```text
Shift + 左ドラッグ
```

を使用します。

## 数値指定

角度欄からZ回転角を直接指定できます。

プリセット：

```text
0°
90°
180°
-90°
```

---

# 20. STEP 4：オルソ面

デフォルトは6面すべてONです。

```text
☑ Front
☑ Back
☑ Left
☑ Right
☑ Top
☑ Bottom
```

必要な面だけ残すこともできます。

---

# 21. 合成オルソの配置

6面を選択した場合：

```text
                 TOP

LEFT          FRONT          RIGHT          BACK

               BOTTOM
```

- TopはFrontの上
- BottomはFrontの下
- Left / Front / Right / Backは横並び

全投影面は同一縮尺です。

---

# 22. 面間隔

GUI：

```text
面間隔 [ 10.0 mm ]
```

デフォルトは10 mmです。

これはグリッド間隔ではありません。

合成オルソ画像内で、各投影面のモデルBBoxどうしを離す実寸間隔です。

入力単位が `m` の場合：

```text
10 mm = 0.01 model unit
```

として内部換算します。

---

# 23. オルソ表現

デフォルトは利用可能なものをすべてONです。

```text
☑ テクスチャ / 頂点カラー
☑ テクスチャ / 頂点カラー + Normal
☑ Normalのみ（シェード）
```

## Texture

外観情報を優先し、照明シェーディングを抑えた表示です。

## Texture + Normal

テクスチャまたは頂点カラーにNormal由来の陰影を加えます。

## Normalのみ（シェード）

外観情報を使わず、単色サーフェスをNormalでシェーディングします。

---

# 24. 合成PNG

通常は、選択した面を1枚に組み合わせたPNGを表現ごとに出力します。

例：

```text
0001_ortho_texture.png
0001_ortho_texture_normal.png
0001_ortho_shade.png
```

6面×3表現でも、標準出力は18枚ではなく3枚です。

---

# 25. 各面を個別出力

GUI：

```text
☐ 各面を個別PNGでも出力
```

デフォルトはOFFです。

ONにすると合成PNGに加え、例えば：

```text
0001_front_texture.png
0001_back_texture.png
0001_top_texture.png
0001_front_shade.png
...
```

も保存します。

個別画像も合成画像と同じ縮尺でレンダリングします。

---

# 26. スケールバー

選択肢：

```text
20 mm
50 mm
100 mm
```

デフォルト：

```text
50 mm
```

スタイル：

```text
             50 mm
├────────────────────────┤
```

- 黒線のみ
- 左右端に短い縦線
- 数値＋単位はバー中央の真上
- 文字列全体を中央揃え
- 合成PNG左下に配置

スケールバーは画像のピクセル寸法とモデルの実寸換算から描画します。

---

# 27. STEP 5：保存して次へ

姿勢・正面・オルソ設定を確認したら：

```text
[保存して次へ]
```

を押します。

現在のファイルを保存した後、次の未処理ファイルを自動的に読み込みます。

v0.1.4では保存欄に進捗表示を追加しています。

```text
正規化モデルを書き出し
Transform情報を書き出し
オルソPNG生成
出力フォルダ確定
```

大きいモデルでも、どの段階を処理中かGUIで確認できます。

---

# 28. 標準出力例

入力：

```text
input/0001.obj
```

標準出力：

```text
output/
└── 0001/
    ├── 0001_rev.obj
    ├── 0001_ortho_texture.png
    ├── 0001_ortho_texture_normal.png
    ├── 0001_ortho_shade.png
    ├── transform.json
    ├── transform_matrix.csv
    └── transform_matrix_cloudcompare.txt
```

OBJの場合、必要に応じてMTLやテクスチャ画像も同じフォルダへ出力されます。

GLBの場合：

```text
output/
└── 0003/
    ├── 0003_rev.glb
    ├── 0003_ortho_texture.png
    ├── 0003_ortho_texture_normal.png
    ├── 0003_ortho_shade.png
    ├── transform.json
    ├── transform_matrix.csv
    └── transform_matrix_cloudcompare.txt
```

---

# 29. transform.json

変換結果だけでなく、正規化条件も保存します。

主な内容：

- 元ファイル名
- SHA-256
- 入力単位
- Normal状態
- 外観情報
- 姿勢決定方式
- 初期Slice軸
- Rim / Base / Manual基準面
- 姿勢確定後Slice中心軸
- 中心軸とZ軸の角度
- 正面Z回転角
- raw → normalized 4×4行列
- inverse matrix
- オルソ面
- 面間隔
- オルソ表現
- 個別画像出力の有無
- スケールバー長

---

# 30. transform_matrix.csv

4行×4列の数値だけを書き出します。

例：

```text
0.9981,-0.0612,0.0043,-12.482
0.0613,0.9978,-0.0311,8.214
-0.0024,0.0313,0.9995,-153.770
0,0,0,1
```

この行列は常に：

```text
raw → normalized
```

です。

列ベクトル表記では：

```text
p_normalized = M × [x, y, z, 1]^T
```

です。

---

# 31. CloudCompare用TXT

```text
transform_matrix_cloudcompare.txt
```

は同じ4×4行列を空白区切りで保存します。

例：

```text
0.9981 -0.0612 0.0043 -12.482
0.0613 0.9978 -0.0311 8.214
-0.0024 0.0313 0.9995 -153.770
0 0 0 1
```

高解像度の元モデルなどへ同じ姿勢変換を適用する用途を想定しています。

---

# 32. GLBについて

GLBは単一メッシュだけでなく、複数geometry、scene transform、material、textureを含むことがあります。

v0.1.4では：

- 姿勢解析用にはScene内のmeshを実座標へ展開して統合
- GLBの `_rev.glb` 出力では元Sceneを保持し、最終TransformをSceneへ適用して再出力

という方法を使用します。

そのため、GLBの正規化モデルでは、Trimeshが保持・再出力できるScene構造やmaterial/textureを可能な限り維持します。

## GLB表示上の制限

複数geometry・複数materialを持つ複雑なGLBでは、GUI表示およびオルソ描画用の統合meshについて、外観を頂点カラーへ変換する場合があります。

この場合：

- `_rev.glb` は元Sceneを基準に保存
- GUI / オルソ表示は統合表示用mesh

という違いがあります。

---

# 33. OBJテクスチャについて

典型的な単一マテリアルOBJではUVとtexture imageを表示・オルソ出力に使用します。

複雑な複数material OBJでは、ライブラリ側の読み込み結果によって頂点カラーへ変換される場合があります。

---

# 34. PLYについて

PLYに頂点カラーがある場合は外観表示に使用します。

頂点カラーが無いPLYでは：

```text
Normalのみ（シェード）
```

だけがオルソ出力可能です。

---

# 35. よくある操作の流れ

```text
1. inputへOBJ / PLY / GLBを入れる
        ↓
2. python app.py
        ↓
3. 先頭の未処理ファイルを自動読込
        ↓
4. 単位を確認
        ↓
5. Mesh QA確認
        ↓
6. Slice / Rim / Base / Manualで水平・傾き決定
        ↓
7. 原点自動設定
        ↓
8. Z軸回転で正面決定
        ↓
9. オルソ面・表現・間隔・スケールバーを確認
        ↓
10. 保存して次へ
        ↓
11. 次の未処理ファイルを自動読込
```

---

# 36. 途中で終了してもよいか

問題ありません。

終了済み個体には `output/<stem>/` があるため、次回起動時に自動スキップします。

未処理の先頭から再開します。

---

# 37. inputへファイルを追加した場合

GUIの：

```text
[inputフォルダを再読込]
```

を押します。

処理済みフォルダを除外して、未処理キューを作り直します。

---

# 38. トラブルシューティング

## GUIが起動しない

仮想環境が有効か確認します。

macOS：

```bash
source .venv/bin/activate
python app.py
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

## ModuleNotFoundError

```bash
python -m pip install -r requirements.txt
```

を再実行してください。

## inputのモデルが表示されない

対応拡張子を確認してください。

```text
.obj
.ply
.glb
```

STLは読み込みません。

## PLYなど大きいモデルを表示した直後にGUIが固まる / 反応が非常に遅い

v0.1.1では、PyVistaQt の `QtInteractor` が既定の自動更新で継続的に再描画し、さらに Normal シェーディング時に PyVista 側で Normal を再計算する場合がありました。70万 faces 前後のモデルでは、macOS などでGUIが実質的に操作不能になることがありました。

v0.1.4では次の対策を行っています。

- `QtInteractor(auto_update=False)` とし、必要なときだけ明示的に再描画
- `multi_samples=0` として対話表示時のアンチエイリアス負荷を軽減
- ファイル読み込み時に検証・計算した vertex normal をPyVistaへ渡し、Normalシェーディング時の重複計算を回避
- 解析・保存には常に元の全解像度メッシュを使用

なお、`output/` フォルダはアプリ起動時に自動生成されます。中が空であることはエラーではありません。個体別の出力フォルダと成果物は「保存して次へ」が正常完了した時点で作成されます。

もしv0.1.4でも表示直後に操作不能になる場合は、ターミナルに表示されたエラー・警告と、次のコマンド結果を確認してください。

```bash
python -c "import pyvista, pyvistaqt, vtk, PySide6; print('PyVista', pyvista.__version__); print('PyVistaQt', pyvistaqt.__version__); print('VTK', vtk.vtkVersion.GetVTKVersion()); print('PySide6', PySide6.__version__)"
```

## v0.1.4で修正したGUIイベントエラー

v0.1.2では `eventFilter()` がマウスイベント以外の `QEvent` / `QPaintEvent` に対しても
`event.modifiers()` を呼び出し、ターミナルへ `AttributeError` を連続出力する不具合がありました。

v0.1.4では、MouseButtonPress / MouseMove / MouseButtonReleaseだけを処理し、
Shift状態は `QApplication.keyboardModifiers()` で取得するよう修正しています。

## 「保存して次へ」でoutput処理が止まる / `zsh: terminated` になる

v0.1.2では、正規化モデルを書き出す直前にTrimeshへvertex normalを再計算させていました。
大きいメッシュではTrimeshがSciPy sparse matrixを利用しようとし、SciPyが無い環境では
fallback計算へ移るため、メモリ使用量が大きくなる場合がありました。

v0.1.4ではこの再計算を廃止しました。

- Normalはファイル読込時に一度だけ計算・検証
- 姿勢TransformではNormalベクトルだけを回転
- OBJ / PLY出力時には回転済みNormalをTrimeshへ直接渡す
- **SciPyをNormal再計算のために追加する必要はありません**

オルソPNG生成も変更しました。

- v0.1.2：面ごとに大きいPolyDataをdeep copyし、新しいoff-screen Plotterを作成
- v0.1.4：**1表現モードにつき1つのoff-screen Plotter**を使い、カメラだけを6方向へ切替

これにより700k-face級モデルのoutput時メモリピークを抑えます。
保存中はGUIの進捗欄で現在の処理段階を表示します。

## ファイルがスキップされる

同名のフォルダが `output` に存在していないか確認してください。

例：

```text
output/0001/
```

があれば `input/0001.obj` は処理済みです。

## 再実行したい

該当出力フォルダを削除し、「inputフォルダを再読込」を押します。

---

# 39. v0.1.4でまだ行っていないこと

- STL対応
- 石器の基部・末端、腹面・背面の完全自動semantic判定
- 土器の「正面」の自動判定
- オルソ解像度のユーザー数値指定
- 複雑な複数materialモデルの完全なレンダラー互換性保証

正面については意図的に人間がZ軸回転で決定する仕様です。

---

# 40. requirements

主なPythonモジュール：

- NumPy
- Trimesh
- PyVista
- PyVistaQt
- PySide6
- Pillow

SciPyはv0.1.4の必須依存ではありません。Normalはアプリ独自のNumPy処理で計算し、出力時にTrimeshへ再計算させない設計です。

インストールは：

```bash
python -m pip install -r requirements.txt
```

でまとめて行えます。

---

# 41. ライセンス

## 41.1 ArtifactPoseNormalizer 本体

ArtifactPoseNormalizer の独自コードは、公開リポジトリでは **CC0 1.0 Universal (CC0-1.0)** として公開することを想定しています。

CC0 は、著作権その他の関連する権利を、法令で認められる最大限の範囲で放棄し、パブリックドメインに提供するための仕組みです。

ただし、**CC0 が適用されるのは ArtifactPoseNormalizer の独自コードおよび、リポジトリ内で明示的に CC0 の対象としているファイルだけです。**

本アプリが利用する Python ライブラリや、それらが利用する第三者ライブラリには、それぞれ個別のライセンスが適用されます。これら第三者ライブラリが CC0 になるわけではありません。

主要な直接依存ライブラリは次のとおりです。

- NumPy
- trimesh
- PyVista
- PyVistaQt
- PySide6
- Pillow

本リポジトリでは、これらのライブラリ本体を原則として同梱せず、利用者が次のコマンドで各配布元から取得する方式を採用します。

```bash
python -m pip install -r requirements.txt
```

この配布形態では、ArtifactPoseNormalizer のソースコードを CC0 とすることと、各依存ライブラリのライセンスは分離して扱われます。

公開時には、リポジトリ直下に CC0-1.0 の正式な `LICENSE` ファイルを置くことを推奨します。

## 41.2 PySide6 / Qt のライセンスについて

本アプリの GUI は **PySide6 (Qt for Python)** を使用しています。

Qt for Python は Qt Company により、**LGPLv3 / GPLv3 / Qt Commercial License** の各条件で提供されています。

公式情報：

- Qt for Python: https://doc.qt.io/qtforpython-6/
- Qt Open Source / LGPL obligations: https://www.qt.io/development/open-source-lgpl-obligations
- Licenses Used in Qt for Python: https://doc.qt.io/qtforpython-6/licenses.html

### 現在の GitHub ソース配布の場合

ArtifactPoseNormalizer の公開リポジトリに PySide6 や Qt の実体をコピーせず、`requirements.txt` に `PySide6` を記載し、利用者自身が `pip` でインストールする場合、**ArtifactPoseNormalizer のリポジトリそのものが PySide6 / Qt を再配布しているわけではありません。**

したがって、本アプリの独自コードを CC0-1.0 として公開しながら、実行時に LGPLv3 等で提供される PySide6 / Qt を利用する構成を取ることができます。

PySide6 / Qt のライセンスは PySide6 / Qt 自身に引き続き適用され、ArtifactPoseNormalizer の CC0 宣言によって変更されることはありません。

### `.app` / `.exe` などを配布する場合

将来、PyInstaller、Nuitka、pyside6-deploy などを利用して、macOS の `.app`、Windows の `.exe`、その他の実行形式を作成し、**PySide6 / Qt のライブラリをアプリケーションに同梱して第三者へ配布する場合は注意が必要です。**

その場合は、単なる ArtifactPoseNormalizer のソース配布とは異なり、PySide6 / Qt 自体の再配布を伴う可能性があります。Qt を LGPLv3 の条件で再配布する場合、Qt Company が示す要件を確認し、それらを満たす必要があります。

Qt Company の LGPL に関する案内では、特に次の事項が挙げられています。

- 利用している LGPL ライブラリと、その変更部分を含む対応ソースコードを利用者が取得できるようにすること。
- LGPL ライブラリを使用していることを明示し、LGPL のライセンス文を利用者へ提供すること。
- 利用者が LGPL ライブラリを変更・置換し、必要に応じて再リンクできる権利を妨げないこと。
- 動的リンクは、アプリケーション本体を LGPL ライブラリから分離して扱うための一般的な方法であること。
- 静的リンク、特殊なパッケージング、変更不能な機器への組み込み等では、追加の要件が生じる可能性があること。
- Qt のすべてのモジュールが必ず LGPL で提供されるわけではなく、使用する Qt モジュールごとのライセンス確認が必要であること。

特に PyInstaller 等で単一実行ファイル化する場合、ライブラリの格納方法や置換可能性が通常の Python 実行環境と異なるため、**「PyInstaller を使えば自動的に LGPL に適合する」とはみなさないでください。** 配布物の構成に応じて、使用している Qt / PySide6 のバージョン、モジュール、同梱方法を確認してください。

また Qt for Python 自身にも、Qt 本体とは別の第三者コンポーネントが含まれる場合があります。Qt の公式ドキュメントは、実際に使用する第三者コンポーネントについて、それぞれのライセンスを確認・表示することを推奨しています。

### GPL の Qt モジュールを使用する場合

Qt の一部の機能・モジュールは、オープンソース利用時に LGPL ではなく GPL のみで提供される場合があります。

そのような GPL 専用モジュールを本アプリで利用するよう将来変更した場合は、ArtifactPoseNormalizer 側にも GPL の条件が及ぶ可能性があります。そのため、新しい Qt モジュールを追加するときは、そのモジュールが LGPL で利用可能かを必ず確認してください。

現在の v0.1.4 は、GUI に PySide6 の基本的な QtCore / QtGui / QtWidgets を利用する構成です。

## 41.3 その他の Python ライブラリ

NumPy、trimesh、PyVista、PyVistaQt、Pillow、および PyVista が利用する VTK なども、それぞれ固有のオープンソースライセンスで提供されています。

本リポジトリではこれらを CC0 の対象には含めません。ライブラリをソースまたはバイナリとしてリポジトリや配布パッケージへ直接同梱する場合は、それぞれの著作権表示、ライセンス文、再配布条件を確認してください。

## 41.4 注意

この README の記載は、ArtifactPoseNormalizer の公開・配布方法を整理するための技術的なライセンス情報です。個別の配布形態についての法的助言ではありません。

特に Qt / PySide6 を含む実行形式を第三者へ配布する場合は、配布時点の Qt 公式ライセンス情報を確認してください。



## v0.1.4 hotfix (PyVista / VTK compatibility)

- Off-screen orthographic rendering no longer passes `multi_samples` to `pyvista.Plotter(...)`.
  Anti-aliasing is disabled after construction with `Plotter.disable_anti_aliasing()`, with a VTK fallback.
- Viewer scale overlay now uses VTK `AddViewProp()` / `RemoveViewProp()` instead of deprecated
  `AddActor2D()` / `RemoveActor2D()` (VTK 9.5 warning cleanup).
- Off-screen `Plotter` cleanup is guarded so a constructor failure cannot trigger a secondary cleanup error.

