# ArtefactsOrthoMaker

**考古資料3Dモデルの姿勢正規化・オルソ展開・曲面展開・計測出力を行うデスクトップGUI**

> **現行バージョン:** **v2.0.1**
>
> **License:** v0.4.10 以降のリリースは **MIT License** です。v0.4.9 以前に **CC0 1.0 Universal** として公開された旧版への適用条件は遡及して変更しません。

<a id="migration-v2"></a>
## v1系列からv2系列への変更

v2.0.0では、AOMを3Dデータのデジタルアーカイブ工程で使う資料出力モジュールとして位置づけました。姿勢確定後の **「資料を書き出す」** で、選択した図版、正規化PLY、変換情報、計測CSV、品質管理JSON、入出力マニフェストを、資料ごとにまとめて保存します。土器ではオルソ・円筒・扇形を複数選択できます。出力方式の切り替え欄で各方式の設定とプレビューを確認し、出力パネルで今回保存する図版を選択してください。

**「一覧表にデータを追加」** は独立した操作です。書き出した処理版のQAと計測値を、`output/inventory-qa-measurements.csv` に1行追記します。初回はCSVを作成し、2回目以降は既存行を保持します。同じ処理版を再度追加するともう1行増えます。石器の断面計測は `sections_json` 列にまとめます。

BagItやレポート生成への受け渡しには `item_manifest.json` を使います。入力の依存関係・SHA-256、出力ファイル別の役割・SHA-256、資料ID・処理版IDを収録します。初期実装の資料IDは入力ファイルの拡張子を除いた名前です。OBJの宣言参照を記録し、外部参照を持つGLBは未対応として記録します。BagItパッケージと人間可読レポートの作成は下流工程で行います。

旧版は [v1.0.0アーカイブ](archive/v1.0.0/README.md) から利用できます。

English: [README_EN.md](README_EN.md)  
開発レポート: [docs/DEVELOPMENT_REPORT.md](docs/DEVELOPMENT_REPORT.md)  
総合コードレビュー: [docs/CODE_REVIEW_v1.0.0.md](docs/CODE_REVIEW_v1.0.0.md)  
Release notes: [docs/RELEASE_NOTES_v1.0.0.md](docs/RELEASE_NOTES_v1.0.0.md)

Repository: https://github.com/kotdijian/ArtefactsOrthoMaker  
制作者：**野口 淳（@fujimicho on X）**

## 目次

- [v1系列からv2系列への変更](#migration-v2)
- [概要](#overview)
- [はじめて使う方へ](#python-environment)
  - [1. Pythonのインストール](#python-install)
  - [2. フォルダ（ディレクトリ）の整備](#folder-setup)
    - [処理対象を置く場所](#input-files)
    - [入力対応ファイル](#supported-input-files)
    - [出力先とスキップ条件](#output-skip)
  - [3. 初期設定と起動](#initial-setup)
    - [macOSの初期設定](#macos-setup)
    - [Windowsの初期設定](#windows-setup)
    - [2回目以降の起動](#run-again)
  - [環境確認スクリプト](#environment-check-script)
  - [よくあるエラー](#troubleshooting)
  - [SELF TEST](#self-test)
  - [更新時の推奨手順](#update-procedure)
- [共通仕様](#common)
- [土器モード](#pottery)
  - [姿勢推定とSliceの判定](#pottery-pose)
- [石器モード](#lithic)
- [画像出力サイズ](#image-output-size)
- [大規模メッシュ](#large-mesh)
- [使用しているPythonモジュール](#python-modules)
- [環境確認](#environment-check)
- [制約](#limitations)
- [ライセンス](#license)
- [開発履歴](#history)


<a id="model-size-warning"></a>
> [!WARNING]
> ## モデルサイズ / メッシュ数について
>
> AOMは自動 decimation を行わず、入力したフルメッシュをそのまま処理します。実用上の目安は、**70万〜100万 faces は余裕の大きい範囲、100万〜200万 faces 程度を推奨範囲、約250万 faces 程度を実用上限の目安**とします。
>
> ASCII OBJ では属性数や数値精度に左右されますが、概ね **200万 faces ≈ 150 MB前後、250万 faces ≈ 200 MB前後**が参考値です。これは厳密な換算ではありません。
>
> **入力ファイルが 300 MB（300,000,000 bytes）を超える場合、読み込み前に警告を表示します。処理は強制中断しません。** 続行するかどうかは利用者が判断できます。300 MB超では Normal 検証、3D表示、オルソ/曲面展開、画像生成でRAM使用量と処理時間が急増する可能性があります。AOMは大規模モデルを点群proxyやdecimated meshへ自動置換しません。

<a id="overview"></a>
## 概要

ArtefactsOrthoMaker は OBJ / PLY / GLB 形式の考古資料3Dモデルを読み込み、**土器**または**石器**として姿勢・座標系を正規化し、研究・記録・DTP用の画像、計測値、正規化モデル、Transform情報を出力する Python / PySide6 GUI アプリです。

主な出力：
- 正規化 PLY
- Transform JSON / CSV / CloudCompare text
- 6面オルソ展開図、SVG輪郭、断面
- 土器円筒展開図 / 扇形展開図
- 曲面展開 settings JSON
- 資料別計測 CSV
- 品質管理JSON、入出力マニフェスト
- QA・計測一覧CSV（専用ボタンで追記）

<a id="python-environment"></a>
<a id="quick-start"></a>
## はじめて使う方へ

初回は **1. Pythonのインストール → 2. フォルダ（ディレクトリ）の整備 → 3. 初期設定と起動** の順に進めてください。コードブロック内のコマンドは、macOSでは「ターミナル」、Windowsでは「PowerShell」に1行ずつ入力し、Enterを押して実行します。

<a id="python-install"></a>
### 1. Pythonのインストール

このアプリは **Python 3.13.x** を推奨します。お使いのOSに合った手順を選んでください。

#### Windows

すでにPowerShellで `py -3.13 --version` を実行して `Python 3.13.x` と表示される場合は、[2. フォルダの整備](#folder-setup)へ進んでください。

1. [Python公式の Install Manager 配布ページ](https://www.python.org/downloads/release/pymanager-264/)を開き、**Download Installer (MSIX)** をクリックします。この `.msix` はx64とARM64の両方に対応します。
2. ダウンロードした `.msix` をダブルクリックし、Windowsの「アプリ インストーラー」で **インストール** を選びます。
3. スタートメニューから新しい **PowerShell** を開き、次の2行を順に実行します。1行目でPython 3.13本体をインストールし、2行目でバージョンを確認します。

```powershell
py install 3.13
py -3.13 --version
```

`Python 3.13.` で始まるバージョンが表示されれば、[2. フォルダの整備](#folder-setup)へ進みます。Pythonが複数入っている場合は、`python --version` が別のバージョンを表示することがあるため、ここではバージョンを指定して確認します。

`py install 3.13` が古いPythonランチャーの影響で動かない場合は、`pymanager install 3.13` でインストールし、`pymanager exec -V:3.13 --version` で確認できます。

#### macOS

すでにターミナルで `python3.13 --version` を実行して `Python 3.13.x` と表示される場合は、[2. フォルダの整備](#folder-setup)へ進んでください。

1. [Python 3.13.17 の公式配布ページ](https://www.python.org/downloads/release/python-31317/#files)の **Files** から **macOS installer** をダウンロードします。Apple SiliconとIntel Macの両方に対応します。
2. ダウンロードした `.pkg` を開き、画面の案内に沿ってインストールします。
3. 新しい「ターミナル」を開き、次を実行します。

```bash
python3.13 --version
```

`Python 3.13.17` のように `3.13.` で始まるバージョンが表示されれば、[2. フォルダの整備](#folder-setup)へ進みます。

<a id="folder-setup"></a>
### 2. フォルダ（ディレクトリ）の整備

1. [GitHubのリポジトリ](https://github.com/kotdijian/ArtefactsOrthoMaker)をブラウザーで開き、緑色の **Code → Download ZIP** を選びます。
2. ダウンロードしたZIPを展開します。WindowsではZIPを右クリックして **すべて展開**、macOSではZIPをダブルクリックします。
3. 展開先を開き、`app.py`、`pose_core.py`、`requirements.txt` が並んでいるフォルダを探します。ZIPで取得した場合、フォルダ名は通常 `ArtefactsOrthoMaker-main` です。このフォルダを以後「プロジェクトフォルダ」と呼びます。ZIPに含まれるファイル一式をそのまま使います。`pose_core.py` は同梱の必須ファイルです。
4. プロジェクトフォルダ内の小文字の `input` フォルダに、処理したい3Dモデルを入れます。フォルダがなければ作成してください。対応形式と出力先は下記のとおりです。

Gitを使っている場合は、ZIPの代わりに `git clone https://github.com/kotdijian/ArtefactsOrthoMaker.git` で取得できます。すでにクローン済みの場合は、`app.py` がある既存のプロジェクトフォルダを使います。

<a id="input-output"></a>
#### `input/`・`output/`・処理キュー

> [!IMPORTANT]
> 実際に使用するフォルダ名は **小文字の `input/` と `output/`** です。Cloneした場合もZIPを展開した場合も、**`app.py` があるフォルダを基準**にします。フォルダ名は小文字でそろえてください。

ArtefactsOrthoMaker は、起動時に `app.py` と同じ階層を作業ルートとして扱います。処理対象はその直下の `input/`、処理結果は同じ作業ルート直下の `output/` に保存します。

```text
ArtefactsOrthoMaker/
├── app.py
├── pose_core.py
├── requirements.txt
├── input/                 ← 処理したい3Dモデルを置く
│   ├── pot001.obj
│   ├── pot001.mtl         ← OBJが参照する場合
│   └── pot001.jpg         ← OBJが参照する場合
└── output/                ← 処理結果が保存される
    └── pot001/
        ├── pot001_rev.ply
        ├── transform.json
        └── ...
```

`input` がなければ、`app.py` と同じ場所に小文字で `input` フォルダを作ってください。`output` はアプリ起動時に自動作成されます。

<a id="input-files"></a>
##### 処理対象を置く場所

処理したい `.obj` / `.ply` / `.glb` を、CloneまたはZIP展開した **ArtefactsOrthoMakerフォルダ内の `input/` に直接置いてください**。

- `input/` のサブフォルダは再帰的には検索しません。処理対象の3Dモデル本体は `input/` 直下に置きます。
- OBJがMTLやJPEG/PNG textureを参照する場合は、OBJからの相対パス関係を保って配置してください。典型的にはOBJ、MTL、texture画像を `input/` に一緒に置きます。
- `.mtl`、`.jpg`、`.png` は3Dモデルの付属ファイルとして利用されますが、それ自体が処理キューへ追加されることはありません。
- 対応3D形式は `.obj`, `.ply`, `.glb` です。STLは対象外です。
- 入力ファイルはファイル名順でキューに並びます。
- 同じstem（拡張子を除いたファイル名）の対応3Dファイルが複数あると、出力先が衝突するため停止します。たとえば `pot001.obj` と `pot001.ply` を同時に `input/` に置かないでください。

<a id="supported-input-files"></a>
##### 入力対応ファイル

処理キューへ追加される**3Dモデル本体**は次の3形式です。

| 種類 | 拡張子 | 扱い |
|---|---|---|
| Wavefront OBJ | `.obj` | 対応。MTL・textureを参照するOBJでは、関連ファイルとの相対パスを保持してください。 |
| Polygon File Format | `.ply` | 対応。vertex colorを含むPLYも利用できます。 |
| glTF Binary | `.glb` | 対応。格納されているappearanceを可能な範囲で利用します。 |
| STL | `.stl` | **非対応**。処理キューには追加されません。 |

OBJで外観情報を使用する場合、次のような**付属ファイル**も `input/` に置くことがあります。

| 付属ファイル | 例 | 扱い |
|---|---|---|
| Material file | `.mtl` | OBJから参照される場合に使用。単独では処理対象になりません。 |
| Texture image | `.jpg`, `.jpeg`, `.png` など | MTL / OBJから参照される場合に使用。単独では処理対象になりません。 |

たとえば、texture付きOBJなら次のように配置します。

```text
ArtefactsOrthoMaker/
└── input/
    ├── pot001.obj
    ├── pot001.mtl
    └── pot001.jpg
```

> [!NOTE]
> `input/` に画像やMTLだけを置いても処理キューには表示されません。キュー判定の対象は `.obj`, `.ply`, `.glb` の3Dモデル本体です。

<a id="output-skip"></a>
##### 出力先とスキップ条件

入力ファイルごとに、同じstem名のフォルダを `output/` に使用します。

```text
input/pot001.obj
        ↓
output/pot001/
```

書き出しが完了すると、資料フォルダに `item_manifest.json` が保存されます。初回は `output/<stem>/` に、すでに資料フォルダがある状態で書き出すと `output/<stem>/revisions/<処理版ID>/` に一式を保存します。**「次のファイルへ」** を押すと次の未処理資料に進みます。

起動時、確定済みマニフェストがある資料は処理済みとしてスキップします。旧版との互換のため、資料フォルダが存在して `.aom_in_progress` がない場合も処理済み扱いです。再処理する場合は、既存の資料フォルダを退避してから起動してください。

一覧は `output/inventory-qa-measurements.csv` に保存されます。資料を書き出した後、一覧に登録する場合は次の資料に進む前に **「一覧表にデータを追加」** を押してください。

<a id="initial-setup"></a>
### 3. 初期設定と起動

OSに合った手順に進みます。初回は、アプリ専用の仮想環境 `venv` を作り、`requirements.txt` に記載されたパッケージをまとめて導入します。

<a id="macos-setup"></a>
#### macOS：初回セットアップ

ターミナルで `cd` と半角スペースを入力し、Finderからプロジェクトフォルダをターミナルのウィンドウへドラッグして、Enterを押します。`ls` を実行して `app.py` と `requirements.txt` が表示されることを確認してください。

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

起動する前に、Finderで作業対象の3Dモデル（`.obj`、`.ply`、`.glb`）を、`app.py` と同じ階層にある小文字の `input/` フォルダへコピーしてください。OBJに付属するMTLやテクスチャ画像がある場合は、[処理対象を置く場所](#input-files)に沿って配置します。その後、次のコマンドで起動します。

```bash
python app.py
```

##### macOS の Qt 起動エラー

本プロジェクトの検証では、`.venv` という名前の環境で Qt platform plugin の file flags に関する問題が発生した例があるため、標準手順では仮想環境名を **`venv`** としています。`.venv` が一般に使用不能という意味ではありません。

詳細：[docs/macos_qt_venv_issue.md](docs/macos_qt_venv_issue.md)

最小 Qt 起動確認：

```bash
python -c 'from PySide6.QtWidgets import QApplication; app=QApplication([]); print("QApplication OK"); app.quit()'
```

<a id="windows-setup"></a>
#### Windows / PowerShell：初回セットアップ

エクスプローラーでプロジェクトフォルダを開きます。アドレスバーに `powershell` と入力してEnterを押すと、そのフォルダでPowerShellが開きます。`dir` を実行して `app.py` と `requirements.txt` が表示されることを確認してください。

Python 3.13を指定して、仮想環境を作成します。

```powershell
py -3.13 -m venv venv
```

手順1で `pymanager exec` を使って確認した場合は、代わりに `pymanager exec -V:3.13 -m venv venv` を実行します。

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

起動する前に、エクスプローラーで作業対象の3Dモデル（`.obj`、`.ply`、`.glb`）を、`app.py` と同じ階層にある小文字の `input/` フォルダへコピーしてください。OBJに付属するMTLやテクスチャ画像がある場合は、[処理対象を置く場所](#input-files)に沿って配置します。その後、次のコマンドで起動します。

```powershell
python app.py
```

#### requirements.txt

`requirements.txt` では、アプリが利用する主要な第三者パッケージをversion固定しています。

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

各パッケージの用途は後述の「[使用しているPythonモジュール](#python-modules)」を参照してください。

<a id="run-again"></a>
#### 2回目以降の起動

`app.py` を実行する前に、作業対象のファイルがプロジェクトフォルダ内の `input/` にあることを確認してください。新しく処理するファイルは、先に `input/` へコピーします。初期設定時と同じプロジェクトフォルダをターミナルまたはPowerShellで開き、仮想環境を有効にしてアプリを起動します。

macOS

```bash
source venv/bin/activate
python app.py
```

Windows

```powershell
.\venv\Scripts\Activate.ps1
python app.py
```

Windowsでスクリプトの実行が拒否された場合は、[Windowsの初期設定](#windows-setup)の対処手順を参照してください。処理済みの資料は、[出力先とスキップ条件](#output-skip)に従って自動でスキップされます。

<a id="environment-check-script"></a>
#### `check_environment.py`

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

<a id="troubleshooting"></a>
#### よくあるエラー

##### `ModuleNotFoundError: No module named '...'`

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

##### `No module named 'pose_core'`

`pose_core.py` は pip パッケージではありません。`app.py` と `pose_core.py` が同じリポジトリ内の所定位置にあることを確認してください。

##### `No module named 'scipy'`

SciPy は必須です。個別追加ではなく：

```bash
python -m pip install -r requirements.txt
```

を実行してください。

##### Qt platform plugin エラー

まず：

```bash
python check_environment.py
```

でQtの段階だけが失敗しているか確認してください。macOSでは [docs/macos_qt_venv_issue.md](docs/macos_qt_venv_issue.md) も参照してください。

<a id="self-test"></a>
#### SELF TEST

共通計算コアの簡易テスト：

```bash
python self_test.py
```

正常終了時：

```text
SELF TEST PASSED
```

`self_test.py` は主として姿勢・Normal・メッシュI/O等の共通計算を確認します。土器・石器のGUI操作、3Dビュー、インタラクティブ操作、オルソ・曲面展開は `app.py` を起動して実機確認してください。

<a id="update-procedure"></a>
#### 更新時の推奨手順

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

<a id="common"></a>
# 共通仕様

入力単位は `mm / cm / m`。自動decimationは行いません。texture / vertex colorを可能な範囲で保持し、必要に応じて表示・処理用Normalを計算します。

## OBJ UV seam

OBJは `v` と `vt` が独立indexを持つため、同一幾何頂点が複数UVを参照できます。v1.0.0ではOBJを `process=False, maintain_order=False` で読み込み、必要なrender vertexを分離してUV seamを保持します。OBJ由来UVのV座標はPyVista/VTKへ渡す前に手動反転しません。

## 出力ワークフロー

姿勢決定後は **「資料を書き出す」** で、図版、PLY/Transform、計測、品質管理、マニフェストをまとめて保存します。同じ資料を続けて書き出すと、別の処理版として保存されます。

<a id="pottery"></a>
# 土器モード

正規化後は `+Z` が上、`X-Y` が水平面です。`+Z` を決める基準は姿勢推定モードによって異なります。

<a id="pottery-pose"></a>
## 姿勢推定とSliceの判定

自動推定の **Rim / Base / Slice** は、開口側を先に探して上下を決めます。開口側の根拠が不足する場合は、**Manual (3 points)** で基準面を指定できます。

| モード | `+Z` を決める基準 |
|---|---|
| **Rim** | 推定した口縁の代表面を水平にします。 |
| **Base** | 開口の反対側から底面を推定し、その面を水平にします。球面状の底や底部が欠損した資料では、接地面を定めにくい場合があります。 |
| **Slice** | メッシュを切った断面の対向輪郭が、複数の高さで支持する器軸を鉛直にします。断面中心には、断面内の座標軸の取り方に依存しない幾何中央値を使います。皿・盤状の器形では、口縁の対向輪郭と広い器面の向きから軸を評価します。 |
| **Manual (3 points)** | 画面で指定した3点が作る面を水平にします。 |

Sliceを実行すると、器軸を支持する輪郭の範囲や、断面の取り方を変えたときの軸の安定性に応じて、次のいずれかになります。

| Sliceの判定 | アプリの動作 |
|---|---|
| **採用** | 推定したSliceの姿勢を適用します。 |
| **参考** | 器軸を支持する根拠が限られるため、確認ダイアログで「はい」を選んだ場合に適用します。 |
| **保留** | Sliceの姿勢を適用せず、直前の姿勢を保持します。Rim・Base・Manualで姿勢を決め直せます。 |

溢水法で姿勢による容量差を比較するときは、**採用されたSliceを主比較に使い、参考姿勢での試算は区別**します。Rim・Baseとの角度差は比較のための情報です。Sliceを適用して書き出すと、`transform.json` の `posture.pose_quality.slice` に判定・理由と、取得できたRim・Base候補との角度差が記録されます。

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
- **内面**：左右関係を保持して深度を反転します。元の三角形の向きが器軸から外向きの面が裏側から見える箇所は、頂点カラー・テクスチャ・陰影に代えて **青色（RGB `#6699CC`）** で表示します。面の向きは元メッシュの頂点順序に依存します。
- **上面**：展開後3Dメッシュを+Zから見る確認用投影

「上面」は元土器の物理的な口縁上面図ではありません。

<a id="lithic"></a>
# 石器モード

正規化後は `X=幅`, `Y=長さ`, `Z=厚さ`。読込姿勢保持または明示的なminimum-volume OBB姿勢推定を選択できます。中央X-Z断面によるY軸水平化と手動X/Y/Z回転、任意断面出力に対応します。

<a id="image-output-size"></a>
# 画像出力サイズ

印刷scale：150 / 300 dpi、50 / 66.6667 / 100%。

```text
px/mm(source) = dpi / 25.4 × print_scale
```

ファイルサイズ目標：S<=10 MB、M<=50 MB、L<=100 MB、Maximum。基本安全上限は16,384 px/辺・100 MP。大容量画像ではpreflight警告を出し、50%等の縮小出力を選択できます。

<a id="large-mesh"></a>
# 大規模メッシュ

| 規模 | ASCII OBJ概算 | 位置づけ |
|---:|---:|---|
| 70万〜100万 faces | 約50〜75 MB | 余裕の大きい実務範囲 |
| 100万〜200万 faces | 約75〜150 MB | 推奨範囲 |
| 約250万 faces | 約200 MB | 実用上限の目安 |
| 250万〜400万 faces | 約200〜300 MB | 高負荷 |
| 300 MB超 | face数に依存 | 読込前に警告、続行可 |

OBJサイズは `v / vt / vn`、桁数、material記述で変わるため概算です。

<a id="python-modules"></a>
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

<a id="environment-check"></a>
# 環境確認

```bash
python -m pip check
python check_environment.py
python self_test.py
```

macOS Qt/PySide6問題：[docs/macos_qt_venv_issue.md](docs/macos_qt_venv_issue.md)

<a id="limitations"></a>
# 制約

- non-watertight meshではvolume/Normal解釈に注意
- 円筒展開は基準径に依存
- 多段扇形展開はpiecewise frustum approximation
- 強い非回転対称形・把手・複雑なconcavityでは厳密等長展開ではない
- 区分境界faceは現状、face重心判定とclippingを使用
- overlap buffer付き区分展開は未実装
- 大規模モデルはRAMと処理時間に注意

<a id="license"></a>
# ライセンス

v0.4.10以降：MIT License。v0.4.9以前：CC0 1.0 Universal。変更は遡及しません。詳細：[LICENSE_HISTORY.md](LICENSE_HISTORY.md)

本アプリで作成した画像・計測結果・研究成果・業務成果物について制作者名のバイネーム表示は要求しません。ソフトウェア自体の再配布は各versionのlicense条件に従います。

任意ですが、成果物・論文・Webページ・発表資料等に本リポジトリへのリンクと **制作者：野口 淳（@fujimicho on X）** を記載していただけると、利用事例の周知に加え、バグ報告や機能リクエストを本リポジトリへ集約するうえで役立ちます。

<a id="history"></a>
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
| **v2.0.0** | 資料一括出力、品質管理JSON、入出力マニフェスト、QA・計測一覧の独立追記 |
| **v2.0.1** | 円筒・扇形の内面展開で外向きの面の裏側を青色（`#6699CC`）で表示 |
| v2.0.1系列（main） | 土器の開口側を先に推定し、Sliceで対向輪郭に基づく器軸推定と採用・参考・保留の判定を追加 |

通常利用はルートの **`app.py`**。過去版は `archive/versions/` に退避しています。
