# ArtefactsOrthoMaker

**考古資料3Dモデルの姿勢正規化・オルソ展開・曲面展開・計測出力を行うデスクトップGUI**

> **Stable release:** **v1.0.0** は通常利用を想定した安定版です。
>
> **License:** v0.4.10 以降のリリースは **MIT License** です。v0.4.9 以前に **CC0 1.0 Universal** として公開された旧版への適用条件は遡及して変更しません。

English: [README_EN.md](README_EN.md)  
開発レポート: [docs/DEVELOPMENT_REPORT.md](docs/DEVELOPMENT_REPORT.md)  
Release notes: [docs/RELEASE_NOTES_v1.0.0.md](docs/RELEASE_NOTES_v1.0.0.md)

Repository: https://github.com/kotdijian/ArtefactsOrthoMaker  
制作者：**野口 淳（@fujimicho on X）**

> [!WARNING]
> ## モデルサイズ / メッシュ数について
>
> v1.0.0 は自動 decimation を行わず、入力したフルメッシュをそのまま処理します。実用上の目安は、**70万〜100万 faces は余裕の大きい範囲、100万〜200万 faces 程度を推奨範囲、約250万 faces 程度を実用上限の目安**とします。
>
> ASCII OBJ では属性数や数値精度に左右されますが、概ね **200万 faces ≈ 150 MB前後、250万 faces ≈ 200 MB前後**が参考値です。これは厳密な換算ではありません。
>
> **入力ファイルが 300 MB（300,000,000 bytes）を超える場合、読み込み前に警告を表示します。処理は強制中断しません。** 続行するかどうかは利用者が判断できます。300 MB超では Normal 検証、3D表示、オルソ/曲面展開、画像生成でRAM使用量と処理時間が急増する可能性があります。v1.0.0 は大規模モデルを点群proxyやdecimated meshへ自動置換しません。

## 概要

ArtefactsOrthoMaker は OBJ / PLY / GLB 形式の考古資料3Dモデルを読み込み、**土器**または**石器**として姿勢・座標系を正規化し、研究・記録・DTP用の画像、計測値、正規化モデル、Transform情報を出力する Python / PySide6 GUI アプリです。

主な出力：
- 正規化 PLY
- Transform JSON / CSV / CloudCompare text
- 6面オルソ展開図、SVG輪郭、断面
- 土器円筒展開図 / 扇形展開図
- 曲面展開 settings JSON
- 資料別計測 CSV
- geometry / 3D model inventory

## インストール

リポジトリ全体を Clone または ZIP で取得してください。**app.py だけを単独で取得しないでください。**

推奨：Python 3.13.x

```bash
git clone https://github.com/kotdijian/ArtefactsOrthoMaker.git
cd ArtefactsOrthoMaker
python3.13 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
python check_environment.py
python app.py
```

対応入力：`.obj`, `.ply`, `.glb`。STLは対象外です。

# 共通仕様

入力単位は `mm / cm / m`。自動decimationは行いません。texture / vertex colorを可能な範囲で保持し、必要に応じて表示・処理用Normalを計算します。

## OBJ UV seam

OBJは `v` と `vt` が独立indexを持つため、同一幾何頂点が複数UVを参照できます。v1.0.0ではOBJを `process=False, maintain_order=False` で読み込み、必要なrender vertexを分離してUV seamを保持します。OBJ由来UVのV座標はPyVista/VTKへ渡す前に手動反転しません。

## 出力ワークフロー

姿勢決定後、計測、展開図、PLY/Transformを独立して繰り返し出力できます。同名ファイルがある場合は **上書き / 別名で保存 / キャンセル** を確認し、「別名で保存」は出力一式へ `_01`, `_02`, … を付与します。

# 土器モード

正規化後は `Z=器軸・高さ`, `X-Y=水平面`。姿勢決定は Slice / Rim / Base / Manual (3 points)。

## 円筒展開

```text
rho   = sqrt(X^2 + Y^2)
theta = atan2(X, -Y)
u     = Rref * theta
v     = Z
```

Front (-Y) が `theta=0`、Back (+Y) がシームです。Zを複数区間へ分け、各区間にZ下端、Z上端、基準Z、基準外径Dを持たせられます。区分点は数値、slider、3Dクリックで指定します。3Dクリックは位置指定専用に消費し、カメラ回転へ入りません。

settings JSONには `breakpoints_z_mm` と各区間の `z0_mm / z1_mm / reference_z_mm / diameter_mm` を保存します。

## 扇形展開

底部・口縁と任意Z区分点の外径から、隣接区間を独立した円錐台として展開します。器壁傾斜が変わる場合、共有円周は3D上で同一でも平面上では異なる曲率の円弧になるため、複数区間を無理に1枚の等長面へ接続しません。

計算式は [開発レポート](docs/DEVELOPMENT_REPORT.md#8-土器の円筒扇形展開アルゴリズム) を参照してください。

## 外面 / 内面 / 上面

- **外面**：展開X-Z形状を外側surface visibilityで描画
- **内面**：左右関係は保持しつつ深度を反転して内側surfaceを描画
- **上面**：展開後3Dメッシュを+Zから見る確認用投影

「上面」は元土器の物理的な口縁上面図ではありません。

# 石器モード

正規化後は `X=幅`, `Y=長さ`, `Z=厚さ`。読込姿勢保持または明示的なminimum-volume OBB姿勢推定を選択できます。中央X-Z断面によるY軸水平化と手動X/Y/Z回転、任意断面出力に対応します。

# 画像出力サイズ

印刷scale：150 / 300 dpi、50 / 66.6667 / 100%。

```text
px/mm(source) = dpi / 25.4 × print_scale
```

ファイルサイズ目標：S<=10 MB、M<=50 MB、L<=100 MB、Maximum。基本安全上限は16,384 px/辺・100 MP。大容量画像ではpreflight警告を出し、50%等の縮小出力を選択できます。

# 大規模メッシュ

| 規模 | ASCII OBJ概算 | 位置づけ |
|---:|---:|---|
| 70万〜100万 faces | 約50〜75 MB | 余裕の大きい実務範囲 |
| 100万〜200万 faces | 約75〜150 MB | 推奨範囲 |
| 約250万 faces | 約200 MB | 実用上限の目安 |
| 250万〜400万 faces | 約200〜300 MB | 高負荷 |
| 300 MB超 | face数に依存 | 読込前に警告、続行可 |

OBJサイズは `v / vt / vn`、桁数、material記述で変わるため概算です。

# 使用しているPythonモジュール

| モジュール / パッケージ | 主な用途 |
|---|---|
| `numpy` | 頂点・face配列、座標・行列・画像配列 |
| `scipy` / `scipy.ndimage` | OBB関連処理、断面fill補修 |
| `trimesh` | OBJ / PLY / GLB I/O、OBB、計測、export |
| `pyvista` | 3D表示、off-screen rendering、VTK wrapper |
| `pyvistaqt` | PyVistaのQt埋め込み |
| `vtkmodules` / VTK | cutter / stripper / plane / picker / image処理 |
| `PySide6` | GUI / event処理 |
| `PIL` (Pillow) | PNG生成・合成、輪郭・断面・scale bar |
| `QtPy` | PyVistaQt依存のQt abstraction |

標準ライブラリでは `csv`, `io`, `json`, `math`, `shutil`, `sys`, `tempfile`, `traceback`, `pathlib`, `time`, `xml.etree.ElementTree`, `itertools`, `hashlib`, `struct`, `dataclasses`, `typing` 等を使用します。ローカル `pose_core.py` がMeshAsset、姿勢推定、Transform、mesh I/Oの共通コアです。

検証済みversionは [requirements.txt](requirements.txt)。

# 環境確認

```bash
python -m pip check
python check_environment.py
python self_test.py
```

macOS Qt/PySide6問題：[docs/macos_qt_venv_issue.md](docs/macos_qt_venv_issue.md)

# 制約

- non-watertight meshではvolume/Normal解釈に注意
- 円筒展開は基準径に依存
- 多段扇形展開はpiecewise frustum approximation
- 強い非回転対称形・把手・複雑なconcavityでは厳密等長展開ではない
- 区分境界faceは現状、face重心判定とclippingを使用
- overlap buffer付き区分展開はv1.0.0では未実装
- 大規模モデルはRAMと処理時間に注意

# ライセンス

v0.4.10以降：MIT License。v0.4.9以前：CC0 1.0 Universal。変更は遡及しません。詳細：[LICENSE_HISTORY.md](LICENSE_HISTORY.md)

本アプリで作成した画像・計測結果・研究成果・業務成果物について制作者名のバイネーム表示は要求しません。ソフトウェア自体の再配布は各versionのlicense条件に従います。

# 開発履歴

| Version | 主な変更 |
|---|---|
| v0.1.x | 土器姿勢推定、Z-up、基本オルソ |
| v0.2–0.3 | 石器モード、OBB、3軸回転、断面 |
| v0.4.0–0.4.5 | 計測、断面、6面図、AABB表示 |
| v0.4.6 | 石器読込姿勢保持 |
| v0.4.7 | 石器split export |
| v0.4.8 | print-scale / file-size raster出力 |
| v0.4.9 | 土器円筒・扇形展開 |
| v0.4.10 | 曲面展開workflow、manual Z breakpoints |
| **v1.0.0** | OBJ UV seam修正、外面/内面/上面、円筒区分点、Zクリック時camera回転抑制、上書き確認と`_01`連番、settings JSON強化、300 MB超警告、raster縮小preflight、stable repository整理 |

通常利用はルートの **`app.py`**。過去版は `archive/versions/` に退避しています。
