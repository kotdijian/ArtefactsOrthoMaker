# ArtefactsOrthoMaker v1.0.0 — Release checklist

## Repository preparation
- [x] root app.py = v1.0.0 RC5 source
- [x] README / README_EN updated
- [x] model-size and >300 MB warning documented
- [x] Python module list added
- [x] development report added
- [x] MIT LICENSE + license history
- [x] historical apps moved to archive/versions/
- [x] patch files removed
- [x] tracked __pycache__ removed and ignored
- [x] requirements/check_environment/self_test labels updated
- [x] macOS Qt note moved to docs/

## Code checks before tag
- [ ] python -m py_compile app.py pose_core.py
- [ ] python -m pip check
- [ ] python check_environment.py
- [ ] python self_test.py

## GUI smoke test before tag
- [ ] pottery Slice / Rim / Base / Manual
- [ ] pottery ortho preview/export
- [ ] OBJ UV seam texture sample
- [ ] cylindrical one/multiple segments
- [ ] fan one/multiple frustum segments
- [ ] outer / inner / upper
- [ ] 3D Z click does not rotate camera
- [ ] overwrite / Save As _01, _02
- [ ] settings JSON
- [ ] 150 / 300 dpi and S/M/L
- [ ] large-raster reduction prompt
- [ ] >300 MB Continue / Cancel
- [ ] pottery measurement + PLY/Transform
- [ ] lithic loaded pose / OBB / sections / PLY-Transform

## Publication
- [ ] review final diff
- [ ] create tag v1.0.0
- [ ] create GitHub Release using RELEASE_NOTES_v1.0.0.md
- [ ] record tested OS / Python / package versions
