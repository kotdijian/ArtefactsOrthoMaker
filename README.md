# Artifact Pose Normalizer v0.1.1

OBJ / PLY / GLB 形式の土器・石器などの3Dモデルを読み込み、姿勢・座標系を正規化し、正規化モデル、変換行列、標準オルソ画像をまとめて保存するPython GUIアプリです。

v0.1.1では、毎回ファイル選択ダイアログを開く必要はありません。アプリフォルダ内の `input` にモデルを入れると、未処理ファイルをファイル名昇順で順番に読み込みます。

---

## 1. 主な機能

* `input` フォルダの OBJ / PLY / GLB をファイル名昇順で連続処理
* `output/<入力ファイル名>/` の存在を処理済み判定に使用
* 読み込み時に入力単位 `mm / cm / m` を指定
* 入力座標値そのものは拡大・縮小しない
* Normalを読み込み時に検証し、必要なら自動計算
* テクスチャ / 頂点カラーの有無を自動判定
* 水平・傾きの決定方法

  * Slice
  * Rim
  * Base
  * Manual（3点）
* 姿勢確定後にSlice中心軸を求める

  * Sliceモードでは最初に得た中心軸を保持
  * Rim / Base / Manualでは水平決定後にSliceを再実行
* 中心軸と、姿勢決定後BBox下底面との交点をXYZ原点に設定
* 最後にZ軸回転だけを手動操作して「正面」を決定
* 姿勢決定後モデルを `<元ファイル名>_rev.<元と同じ形式>` で保存
* `transform.json` を保存
* raw → normalized の4×4変換行列をCSVで保存
* CloudCompare等で使いやすい空白区切り4×4行列も保存
* 選択した投影面を1枚に組み合わせたオルソPNGを出力
* 必要なら各面PNGも追加出力
* スケールバー 20 / 50 / 100 mm を選択可能（デフォルト50 mm）

---

# 2. 対応形式

## 入力

* `.obj`
* `.ply`
* `.glb`

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
ArtifactPoseNormalizer_v0.1.1/
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

v0.1.1では、保存中だけ

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

## 推奨

* Python 3.12 または 3.13
* macOS / Windows

Apple Silicon Macでも利用できます。

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
cd ~/Downloads/ArtifactPoseNormalizer_v0.1.1
```

分からない場合は、

1. `cd ` と入力
2. 半角スペースを入れる
3. Finderから `ArtifactPoseNormalizer_v0.1.1` フォルダをターミナルへドラッグ
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
cd C:\Users\ユーザー名\Downloads\ArtifactPoseNormalizer_v0.1.1
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

v0.1.1のSELF TESTは次を確認します。

1. 深い器形のSlice中心軸推定
2. 浅い器形のSlice中心軸推定
3. GLB読込
4. GLBの `_rev.glb` 再出力

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

* オルソ面間隔 10 mm
* スケールバー 20 / 50 / 100 mm

を入力モデル座標へ換算するために使用します。

## 読み込み後に単位を変更してもよい

v0.1.1では単位を変更してもメッシュを読み直す必要はありません。

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

* OBJ：`vn` の有無を確認
* PLY：`nx / ny / nz` の有無を確認
* GLB：GLB内部の `NORMAL` attributeを確認

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

* テクスチャ画像を持たないOBJ
* 頂点カラーを持たないPLY
* 利用可能な外観情報を取得できないGLB

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

* TopはFrontの上
* BottomはFrontの下
* Left / Front / Right / Backは横並び

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

* 黒線のみ
* 左右端に短い縦線
* 数値＋単位はバー中央の真上
* 文字列全体を中央揃え
* 合成PNG左下に配置

スケールバーは画像のピクセル寸法とモデルの実寸換算から描画します。

---

# 27. STEP 5：保存して次へ

姿勢・正面・オルソ設定を確認したら：

```text
[保存して次へ]
```

を押します。

現在のファイルを保存した後、次の未処理ファイルを自動的に読み込みます。

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

* 元ファイル名
* SHA-256
* 入力単位
* Normal状態
* 外観情報
* 姿勢決定方式
* 初期Slice軸
* Rim / Base / Manual基準面
* 姿勢確定後Slice中心軸
* 中心軸とZ軸の角度
* 正面Z回転角
* raw → normalized 4×4行列
* inverse matrix
* オルソ面
* 面間隔
* オルソ表現
* 個別画像出力の有無
* スケールバー長

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

v0.1.1では：

* 姿勢解析用にはScene内のmeshを実座標へ展開して統合
* GLBの `_rev.glb` 出力では元Sceneを保持し、最終TransformをSceneへ適用して再出力

という方法を使用します。

そのため、GLBの正規化モデルでは、Trimeshが保持・再出力できるScene構造やmaterial/textureを可能な限り維持します。

## GLB表示上の制限

複数geometry・複数materialを持つ複雑なGLBでは、GUI表示およびオルソ描画用の統合meshについて、外観を頂点カラーへ変換する場合があります。

この場合：

* `_rev.glb` は元Sceneを基準に保存
* GUI / オルソ表示は統合表示用mesh

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

# 39. v0.1.1でまだ行っていないこと

* STL対応
* 石器の基部・末端、腹面・背面の完全自動semantic判定
* 土器の「正面」の自動判定
* オルソ解像度のユーザー数値指定
* 複雑な複数materialモデルの完全なレンダラー互換性保証

正面については意図的に人間がZ軸回転で決定する仕様です。

---

# 40. requirements

主なPythonモジュール：

* NumPy
* Trimesh
* PyVista
* PyVistaQt
* PySide6
* Pillow

インストールは：

```bash
python -m pip install -r requirements.txt
```

でまとめて行えます。
