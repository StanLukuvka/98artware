# vmdisp9x licence research (R6a), 2026-11-13

Not legal advice. Read-only page fetches; nothing downloaded.

## 1. vmdisp9x licence
- Root `LICENSE` is MIT: "Copyright (c) 2022 JHRobotics"
  https://raw.githubusercontent.com/JHRobotics/vmdisp9x/main/LICENSE
- Whole repo? Partly unconfirmed. `ddk/` (10 headers: ddrawi.h, dibeng.h, gdidefs.h, minivdd.h ...) is
  "directly derived from the Win9x DDK" (Microsoft). No separate licence file in `ddk/`.
  https://raw.githubusercontent.com/JHRobotics/vmdisp9x/main/readdev.txt
  https://api.github.com/repos/JHRobotics/vmdisp9x/contents/ddk
- `fixlink/` is a git submodule (c1fd1d2); its licence is unconfirmed.
- Release assets: no licence file is listed as an asset. Contents of the zip/ima are unconfirmed
  (not downloaded; the release page shows asset names only).
  https://github.com/JHRobotics/vmdisp9x/releases

## 2. Upstream chain
- QEMU `-vga std` support: README credits Philip Kelley's modification: "modified VBE driver (`qemumini.drv`)".
  https://github.com/JHRobotics/vmdisp9x
- phkelley/boxv9x: "modification of the OS/2 Museum's boxv9x display driver" (fork of volkertb/boxv9x).
  No LICENSE file seen. Licence: unconfirmed (none stated).
  https://github.com/phkelley/boxv9x
- volkertb/boxv9x: "Cloned from .../www.os2museum.com/hg/boxv9x/". No LICENSE file seen; unconfirmed.
  https://github.com/volkertb/boxv9x
- OS/2 Museum (Michal Necasek) source post: "As promised, here is the source code". No licence text on the page.
  https://www.os2museum.com/wp/windows-9x-video-minidriver-source-code/
- Further upstream: Win9x DDK sample code (Microsoft). readdev.txt: driver "similar to Windows 95/98 DDK sample code";
  "The DDK is not used or required to build this driver."
  Also Open Watcom 1.9 for the build (not a runtime dependency).
- Forbidding terms: none found on any page read. But the upstream boxv9x lineage has NO stated licence and the
  `ddk/` files carry Microsoft DDK provenance (original DDK licence terms unconfirmed). Absence of a statement is
  not permission. The MIT label on vmdisp9x cannot grant rights JHRobotics does not hold in the derived parts.

## 3. Compatibility with an MIT tool (analysis, not evidence-backed)
- Download from upstream at user request, pin sha256, install into the user's own image: art98 neither copies nor
  redistributes the binary; the user obtains it from the author. Low risk. The art98 MIT licence is untouched
  (separate work, no linking).
- Modified INF in art98 repo: vmdisp9x.inf is part of the MIT-labelled repo, so a derived INF is plausible under
  MIT with attribution (keep the copyright + MIT notice). Residual risk: the INF's hardware ID / mode lists
  derive from the boxv9x lineage (no stated licence). Safer option: ship a render-at-install script that
  patches the downloaded INF on the user's machine (no INF text in repo), or a minimal original INF.
- Recommendation: add a THIRD-PARTY note naming vmdisp9x (MIT, JHRobotics), boxv9x (OS/2 Museum; P. Kelley),
  Win9x DDK-derived headers; ask the upstream author to confirm if the INF is committed.

## 4. Win98 SE and QEMU -vga std
- README: "Supported adapters are `-vga std` which using modified VBE driver (`qemumini.drv`)."
  README itself only says "Windows 95/98/Me"; no explicit "98 SE" (unconfirmed in README/docs).
  https://github.com/JHRobotics/vmdisp9x
- Search snippet (secondary, not read directly): a VOGONS post recommends 98 SE for fresh install;
  QEMU support since v1.2023.0.10; Aug 2025 note "fixed page fault in ... QEMU std vga driver".
  https://www.vogons.org/viewtopic.php?p=1163950 (snippet only, unconfirmed)
- No issue with 98 SE + `-vga std` + QEMU version found. QEMU version tested: unconfirmed.

## 5. Current release
- v1.2025.0.119, published 2025-07-29 (repacked 2025-08-03, tag suffix "b").
  https://api.github.com/repos/JHRobotics/vmdisp9x/releases/latest
- Assets (bytes): vmdisp9x-1.2025.0.119b-driver-2d.{ima 1474560, img 1474560, zip 355886};
  driver-3d-win95-min.{iso 35407872, iso.xz 3492804, zip 9642068};
  driver-3d-win95.{iso 105420800, iso.xz 14066444, zip 35025579};
  driver-3d-win98.{iso 101038080, iso.xz 14619348, zip 33885454}
  plus GitHub auto source zip/tar.gz.
- The release API page returns no sha256 digests; compute locally on first download.
