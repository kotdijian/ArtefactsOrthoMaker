# macOSにおけるQt / PySide6仮想環境の技術情報

## 1. この文書について

この文書は、Artifact Pose Normalizer v0.1.5 のmacOS検証中に確認した、Python仮想環境とQt / PySide6のplatform pluginに関する現象を記録した技術資料です。

READMEの通常セットアップ手順では、仮想環境名として `venv` を使用します。本資料は、通常利用者向けの必須手順ではなく、同様のQt起動エラーが発生した場合の調査記録です。

重要なのは、**一般論として `.venv` がPythonやPySide6で使用できないという意味ではない**ことです。`.venv` と `venv` はPythonの仮想環境として機能上の違いはなく、名前が異なるだけです。本プロジェクトのmacOS検証環境では、`.venv` 配下でQt pluginのファイル属性に異常が発生する現象を確認したため、再現性を優先して `venv` を標準手順に採用しました。

---

## 2. 確認した環境

主な検証環境：

```text
macOS
Apple Silicon / arm64
Python 3.13.7
PySide6 / Qt 6.10.3
PyVista 0.48.4
PyVistaQt 0.12.0
VTK 9.6.2
```

Artifact Pose Normalizer v0.1.4が正常に完走し、最小構成の `QApplication` も起動できることを確認した環境を基準に比較しました。

---

## 3. 症状

Qt / PySide6のGUI起動時に次のエラーが発生しました。

```text
qt.qpa.plugin: Could not find the Qt platform plugin "cocoa" in ""

This application failed to start because no Qt platform plugin could be initialized.
```

この状態ではArtifact Pose Normalizerだけでなく、次の最小コードでも起動できませんでした。

```bash
python -c 'from PySide6.QtWidgets import QApplication; app=QApplication([]); print("QApplication OK"); app.quit()'
```

したがって、アプリケーション固有のGUI処理ではなく、Qt / PySide6のplatform plugin初期化段階で発生している問題と切り分けられます。

---

## 4. 実際に確認したQt pluginの状態

問題発生時、PySide6のQt pluginディレクトリにはplatform plugin自体は存在していました。

```text
PySide6/Qt/plugins/platforms/
├── libqcocoa.dylib
├── libqminimal.dylib
└── libqoffscreen.dylib
```

個別ファイルについては、次を確認できました。

```text
exists      = True
isFile      = True
readable    = True
isLibrary   = True
QPluginLoader.load() = True
```

つまり `libqcocoa.dylib` が欠落していたわけではありません。

一方、問題発生時にはPySide6のQt plugin `.dylib` 70個にmacOSの `UF_HIDDEN` フラグが付与されていました。

platform pluginの例：

```text
libqcocoa.dylib
  flags      = 0x8040
  UF_HIDDEN  = True
  QtHidden   = True

libqminimal.dylib
  flags      = 0x8040
  UF_HIDDEN  = True
  QtHidden   = True

libqoffscreen.dylib
  flags      = 0x8040
  UF_HIDDEN  = True
  QtHidden   = True
```

この状態では、Qtの通常のディレクトリ列挙結果が次のようになりました。

```text
QDir visible: []
```

`QDir.Filter.Hidden` を明示した場合には3つのplatform pluginを列挙できたため、Qtがこれらをhidden fileとして扱っていることも確認しました。

---

## 5. `UF_HIDDEN` と起動エラーの関係

macOSの `UF_HIDDEN` はファイルシステム上のhidden属性です。

今回の検証では、Qt pluginがファイルとして存在し、直接ロード可能であっても、`UF_HIDDEN=True` の状態ではQtの通常のplugin探索から見えなくなっていました。

その結果、macOS GUIに必要な `cocoa` platform pluginをQtが自動検出できず、`QApplication` の生成時に失敗する状態と整合しました。

ただし、本資料では次の点を区別します。

- **確認済み**：問題発生時にQt plugin 70個へ `UF_HIDDEN` が付いていた。
- **確認済み**：その状態ではQtの通常列挙からplatform pluginが見えなかった。
- **確認済み**：`.venv` 環境では、一度 `UF_HIDDEN` を解除しても後の別Pythonプロセスで再び70個がhiddenになる現象を確認した。
- **確認済み**：同じプロジェクトで仮想環境名を `venv` として再構築すると、v0.1.4完走後の別Pythonプロセスでも `QApplication` が正常起動した。
- **未確定**：なぜ `.venv` 配下で `UF_HIDDEN` が再付与されたかというOSレベルの発生機序。
- **一般化しない**：`.venv` という名前自体がmacOSやPySide6で常に問題になるとは判断していない。

---

## 6. 本プロジェクトで採用した対策

Artifact Pose Normalizerでは、macOSの標準セットアップ手順を次のようにしています。

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

この構成では、検証時に以下を確認しました。

```text
v0.1.4 完走
↓
別Pythonプロセスで QApplication OK
↓
v0.1.5 起動
↓
GUI Normalシェード表示 OK
```

そのため、アプリケーション側に `chflags` などのQt plugin修復処理は組み込んでいません。

アプリ自身が仮想環境内のライブラリ属性を書き換える方式は採用せず、正常に動作する仮想環境を構築する方針としています。

---

## 7. `.venv` と `venv` の違い

Pythonの `venv` モジュールから見れば、次の2つに機能上の違いはありません。

```bash
python3 -m venv .venv
python3 -m venv venv
```

違いはディレクトリ名です。

```text
.venv  = Unix系OSではドットで始まる隠しディレクトリ名
venv   = 通常のディレクトリ名
```

`.venv` は一般的なPython開発でも広く使用されています。本プロジェクトで `venv` を採用するのは、今回のmacOS検証環境で確認したQt plugin問題を回避し、Mac / Windowsで手順を統一するためです。

---

## 8. 同様の症状が発生した場合の確認

まずArtifact Pose Normalizerではなく、最小のQt起動テストを行います。

```bash
python -c 'from PySide6.QtWidgets import QApplication; app=QApplication([]); print("QApplication OK"); app.quit()'
```

ここでも `cocoa` エラーになる場合は、アプリケーション固有処理ではなくQt環境側を確認します。

platform pluginの場所はPythonから確認できます。

```bash
python - <<'PYCODE'
from pathlib import Path
from PySide6.QtCore import QLibraryInfo

p = Path(
    QLibraryInfo.path(QLibraryInfo.LibraryPath.PluginsPath)
) / "platforms"

print(p)
PYCODE
```

本プロジェクトで確認した代表的なplatform pluginは次の3つです。

```text
libqcocoa.dylib
libqminimal.dylib
libqoffscreen.dylib
```

macOSのfile flagsを確認する場合：

```bash
ls -lO venv/lib/python3.13/site-packages/PySide6/Qt/plugins/platforms/
```

`hidden` が表示される場合は、本資料で記録した現象と同種の可能性があります。

---

## 9. 再構築を優先する理由

問題発生時に個々のQt pluginへ対して `chflags nohidden` を実行することは技術的には可能です。しかし今回の検証では、`.venv` 環境で解除後に再び `UF_HIDDEN` が付与される現象を確認しました。

そのため本プロジェクトでは、恒久対策としてアプリ起動時に属性を書き換えるのではなく、次の手順を優先します。

1. 問題のある仮想環境をアプリ本体から切り離す。
2. `venv` という名前で仮想環境を新規作成する。
3. `requirements.txt` から依存ライブラリを再導入する。
4. 最小 `QApplication` で起動確認する。
5. `python app.py` で動作確認する。

---

## 10. 現時点の結論

Artifact Pose Normalizer v0.1.5 のmacOS検証では、`.venv` 配下のPySide6 Qt pluginに `UF_HIDDEN` が付与され、Qtの通常のplugin探索からplatform pluginが見えなくなる現象を確認しました。

発生機序そのものは未確定ですが、`venv` という名前で仮想環境を再構築した環境では、v0.1.4完走後の別プロセスでもQtが正常起動し、v0.1.5のGUI Normalシェード表示も確認できました。

したがって、本プロジェクトのREADMEではMac / Windowsともに仮想環境名を `venv` に統一しています。
