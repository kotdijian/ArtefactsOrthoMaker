# ArtefactsOrthoMaker

**考古資料3Dモデルの姿勢正規化・オルソ展開・曲面展開・計測出力を行うデスクトップGUI**

> **Stable release:** **v1.0.0** は通常利用を想定した安定版です。
>
> **License:** v0.4.10 以降のリリースは **MIT License** です。v0.4.9 以前に **CC0 1.0 Universal** として公開された旧版への適用条件は遡及して変更しません。

English: [README_EN.md](README_EN.md)  
開発レポート: [docs/DEVELOPMENT_REPORT.md](docs/DEVELOPMENT_REPORT.md)  
総合コードレビュー: [docs/CODE_REVIEW_v1.0.0.md](docs/CODE_REVIEW_v1.0.0.md)  
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

## Python 環境・実行方法

リポジトリ全体を **Clone** または **ZIP** で取得してください。**`app.py` だけを単独で取得しないでください。** `pose_core.py`、`requirements.txt`、環境確認・SELF TEST用スクリプトも必要です。

対応入力は `.obj`, `.ply`, `.glb` です。STL は対象外です。

### 1. 推奨フォルダ構成

```text
ArtefactsOrthoMaker/
├── app.py
├── pose_core.py
├── check_environment.py
├── self_test.py
├── requirements.txt
├── README.md
├── README_EN.md
├── LICENSE
├── LICENSE_HISTORY.md
├── docs/
├── archive/
├── input/
└── output/
```

`pose_core.py` は **pip でインストールするライブラリではなく、このアプリに含まれる必須ファイル**です。通常利用では `app.py` と同じリポジトリ内の配置を保ってください。

`input/` と `output/` は存在しない場合、アプリ起動時に作成されます。過去版は `archive/versions/` に保存されています。

### 2. 推奨 Python と最初の確認

**Python 3.13.x** を推奨します。

macOS：

```bash
python3.13 --version
```

Windows PowerShell：

```powershell
python --version
```

`Python 3.13.x` と表示されれば、以下の標準手順を使用できます。

### 3. リポジトリの取得

Git を使用する場合：

```bash
git clone https://github.com/kotdijian/ArtefactsOrthoMaker.git
cd ArtefactsOrthoMaker
```

Git を使用しない場合は、GitHub の **Code → Download ZIP** でリポジトリ全体を取得し、ZIPを展開してから、そのフォルダをターミナル / PowerShell で開いてください。

### 4. macOS：初回セットアップ

ターミナルでプロジェクトフォルダへ移動します。

```bash
cd /path/to/ArtefactsOrthoMaker
```

仮想環境 `venv` を作成・有効化します。

```bash
python3.13 -m venv venv
source venv/bin/activate
```

pip 関係を更新し、`requirements.txt` から必要な外部パッケージをまとめて導入します。

```bash
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

依存関係と実行環境を確認します。

```bash
python -m pip check
python check_environment.py
```

共通計算コアのSELF TESTも実行できます。

```bash
python self_test.py
```

最後にアプリを起動します。

```bash
python app.py
```

#### macOS の Qt 起動エラー

本プロジェクトの検証では、`.venv` という名前の環境で Qt platform plugin の file flags に関する問題が発生した例があるため、標準手順では仮想環境名を **`venv`** としています。`.venv` が一般に使用不能という意味ではありません。

詳細：[docs/macos_qt_venv_issue.md](docs/macos_qt_venv_issue.md)

最小 Qt 起動確認：

```bash
python -c 'from PySide6.QtWidgets import QApplication; app=QApplication([]); print("QApplication OK"); app.quit()'
```

### 5. Windows / PowerShell：初回セットアップ

PowerShell でプロジェクトフォルダへ移動します。

```powershell
cd C:\path\to\ArtefactsOrthoMaker
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
python self_test.py
```

起動：

```powershell
python app.py
```

### 6. requirements.txt

v1.0.0 の `requirements.txt` では、アプリが利用する主要な第三者パッケージをversion固定しています。

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

Python標準ライブラリはPython本体に含まれるため、個別インストールは不要です。また、上記パッケージが必要とする内部依存パッケージは `pip` が自動的に導入します。**個別モジュールを1つずつ追加するのではなく、原則として `requirements.txt` を使用してください。**

各パッケージの用途は後述の「[使用しているPythonモジュール](#使用しているpythonモジュール)」を参照してください。

### 7. `check_environment.py`

依存関係とQt起動環境を確認するスクリプトです。

```bash
python check_environment.py
```

NumPy、SciPy、Trimesh、PyVista、PyVistaQt、VTK、PySide6、QtPy、Pillow、ローカル `pose_core.py`、Qt `QApplication` / platform plugin を順に確認します。

正常な場合、最後に：

```text
ENVIRONMENT CHECK PASSED
```

と表示します。

### 8. よくあるエラー

#### `ModuleNotFoundError: No module named '...'`

まず仮想環境が有効か確認します。

macOS：

```bash
which python
```

`.../ArtefactsOrthoMaker/venv/bin/python` のように表示されるのが正常です。

Windows PowerShell：

```powershell
Get-Command python
```

`...\ArtefactsOrthoMaker\venv\Scripts\python.exe` を指していることを確認します。

その後：

```bash
python -m pip install -r requirements.txt
python -m pip check
python check_environment.py
```

を再実行してください。

#### `No module named 'pose_core'`

`pose_core.py` は pip パッケージではありません。`app.py` と `pose_core.py` が同じリポジトリ内の所定位置にあることを確認してください。

#### `No module named 'scipy'`

SciPy は必須です。個別追加ではなく：

```bash
python -m pip install -r requirements.txt
```

を実行してください。

#### Qt platform plugin エラー

まず：

```bash
python check_environment.py
```

でQtの段階だけが失敗しているか確認してください。macOSでは [docs/macos_qt_venv_issue.md](docs/macos_qt_venv_issue.md) も参照してください。

### 9. SELF TEST

共通計算コアの簡易テスト：

```bash
python self_test.py
```

正常終了時：

```text
SELF TEST PASSED
```

`self_test.py` は主として姿勢・Normal・メッシュI/O等の共通計算を確認します。土器・石器のGUI操作、3Dビュー、インタラクティブ操作、オルソ・曲面展開は `app.py` を起動して実機確認してください。

### 10. 更新時の推奨手順

Git clone した環境を更新する場合：

```bash
git pull
source venv/bin/activate
python -m pip install -r requirements.txt
python -m pip check
python check_environment.py
python self_test.py
```

Windows PowerShellでは `source venv/bin/activate` の代わりに：

```powershell
.\venv\Scripts\Activate.ps1
```

を使用します。

環境が大きく崩れた場合は、個別モジュールを継ぎ足すより `venv` を作り直し、`requirements.txt` から再構築する方が再現性があります。

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

任意ですが、成果物・論文・Webページ・発表資料等に本リポジトリへのリンクと **制作者：野口 淳（@fujimicho on X）** を記載していただけると、利用事例の周知に加え、バグ報告や機能リクエストを本リポジトリへ集約するうえで役立ちます。

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
