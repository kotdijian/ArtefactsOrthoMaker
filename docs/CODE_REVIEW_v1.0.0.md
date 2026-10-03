# ArtefactsOrthoMaker v1.0.0 — 総合コードレビュー

## 1. 結論

v1.0.0をベータ表記から外し、通常利用を想定した安定版として周知することは妥当である。

一方、**将来の保守性・拡張性が十分に担保済みの最終構造とは評価しない**。最大の理由は `MainWindow` にUI、状態管理、rendering、geometry、export、queue、metadataが集中している点である。

したがって方針は次の二段階が適切である。

1. v1.0.0を機能安定版としてreleaseする。
2. 次の大規模feature cycleに入る前にmodule分割とregression test拡充を優先する。

## 2. 現在のコード規模

mainブランチのv1.0.0について静的に確認した。

- `app.py`: 約11,574行 / 約445 KB
- `MainWindow`: 約11,053行
- class-level methods: 約302
- `except Exception`: 73箇所
- `pose_core.py`: 約848行

長い主なmethod：

- `_build_ui`: 約874行
- `export_orthos`: 約309行
- `export_lithic_orthos`: 約249行
- `_export_lithic_orthographic_files`: 約204行
- `_lithic_metadata`: 約199行
- `_fill_section_paths`: 約181行
- `_build_pottery_curve_scene`: 約168行
- `_apply_lithic_oriented_bounds`: 約167行

## 3. 設計上の強み

- `pose_core.py` にMeshAsset、姿勢推定、Transform、mesh I/Oが分離されている。
- 土器Z-up、石器X=幅/Y=長さ/Z=厚さの座標規約が明示されている。
- normalized PLYとTransformを保存でき、再現性が高い。
- 計測、画像、PLY/Transformの出力を分離したworkflowになっている。
- staging / in-progress markerにより途中失敗を完成成果と誤認しにくい。
- v1.0.0ではOBJ UV seam、curve settings JSON、同名出力確認など、再現性とデータ保全が強化されている。

## 4. 主な保守性リスク

### High: MainWindowの責務集中

現在のMainWindowは以下を一つのclassで担当する。

- GUI construction
- pottery/lithic state
- pose controls
- picker / slider events
- PyVista / VTK rendering
- section geometry
- cylindrical / fan development
- raster sizing
- file-size preflight
- inventory / metadata
- export / queue management

機能追加が続くとmode間の副作用、reset漏れ、出力系regressionが増えやすい。

### Medium: 長大methodと分岐

render、geometry、保存、UI通知を同一methodで処理する箇所が多い。pure geometryとI/O/UI boundaryの分離が望ましい。

### Medium: 広い例外捕捉

GUI event boundaryでの `except Exception` は妥当だが、内部geometry/I/Oでは `ValueError`, `RuntimeError`, `OSError` 等へ狭めるべきである。

### Medium: private helper coupling

v1.0.0のOBJ seam-safe loaderはapp側から `pose_core._scene_to_single_mesh`, `_appearance_from_mesh` 等のprivate helperを利用している。正式なmesh I/O APIとしてpose_core側へ統合するのが望ましい。

## 5. 推奨module分割

```text
aom/
  models/
    state.py
    settings.py
  core/
    mesh_io.py
    pose.py
    transforms.py
  pottery/
    pose.py
    cylindrical.py
    fan.py
    orthographic.py
  lithic/
    pose.py
    sections.py
    orthographic.py
  render/
    raster.py
    outline.py
    layout.py
  export/
    metadata.py
    inventory.py
    workflow.py
  ui/
    main_window.py
    pottery_panel.py
    lithic_panel.py
    preview.py
```

安全な移行順：

1. raster sizing / preflightをpure function化
2. cylindrical / fan geometryを独立
3. lithic section geometryを独立
4. export workflowをservice化
5. UI stateをdataclass化

## 6. テスト

v1.0.0 release前に最低限必要：

- `python -m py_compile app.py pose_core.py`
- `python -m pip check`
- `python check_environment.py`
- `python self_test.py`
- OBJ UV seam sample
- cylindrical/fan one- and multi-segment
- outer/inner/upper
- breakpoint click without camera rotation
- overwrite / numbered save
- 300 MB warning
- print-scale / S-M-L raster
- pottery/lithic PLY + Transform

次期版ではpytest + GitHub Actionsを導入し、curve mapping、UV seam、raster sizing、metadataを数値regressionとして固定することを推奨する。

## 7. ライセンスと利用表記

- v0.4.9以前にCC0 1.0 Universalとして公開した版の条件は維持。
- v0.4.10以降はMIT License。
- 変更は遡及しない。
- 本アプリの生成成果物に制作者名のバイネーム表記は要求しない。
- ソフトウェア自体の再配布には各versionのlicense条件が適用される。
- 任意の謝辞としてrepository URLと「制作者：野口 淳（@fujimicho on X）」を記載すると、利用事例の周知、bug report、feature requestの集約に役立つ。

## 8. 安定版release判定

**release checklistのcode checksとGUI smoke testが通れば、v1.0.0のベータ表記解除は妥当。**

ただし次のfeature cycleでは、大きな新機能よりregression testとMainWindow分割を優先する。
