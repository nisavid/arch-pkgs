# Open WebUI 0.11 package closure

Research snapshot: 2026-08-18

Tracker question: [#63](https://github.com/nisavid/arch-pkgs/issues/63)

Accepted parent contract: [#26 resolution](https://github.com/nisavid/arch-pkgs/issues/26#issuecomment-5258698835)

## Conclusion

The G0-G2 implementation should freeze the following core as one coordinated
package set:

- `open-webui` 0.11.0 from the PyPI source archive and the upstream tag at
  commit `f9590b8017199e56d5e953657e6498e3cef1d246`;
- a new `python-rapidocr` 3.9.2 source package at commit
  `095232a4c94f7f0e6600ba5bba1177010ad696d4`, with the three upstream default
  ONNX models packaged as immutable sources;
- `python-sentence-transformers` 5.5.1 at commit
  `ce3ec6d87f25b2d1cccb0a20f8fd495dad5c30fb`;
- the exact Python 3.14 and system-provider matrix below; and
- a private Open WebUI base dependency closure of 220 exact non-system
  distributions, derived from the release's `uv.lock` and installed from a
  committed hash lock.

This is implementable, but G0 has a real artifact-retention prerequisite. The
accepted Python/gfx and scientific provider archives are retained and their
identities are recorded below, but several are no longer listed by the
currently configured repositories. G0 must copy or rebuild those exact
archives into a controlled staging repository before G1 or G2 relies on them.
Source-recipe availability alone is not deployment evidence.

Open WebUI's browser-local Pyodide wheels and WebAssembly are application
frontend assets. They are not server-side duplicates of pacman-owned Python
providers and must not be removed by the server-side externalization audit.

## Immutable application sources

### Open WebUI

The upstream `v0.11.0` tag resolves to
[`f9590b8017199e56d5e953657e6498e3cef1d246`](https://github.com/open-webui/open-webui/commit/f9590b8017199e56d5e953657e6498e3cef1d246).
PyPI publishes both an sdist and wheel for the same release in its
[`0.11.0` release record](https://pypi.org/pypi/open-webui/0.11.0/json).

| Input | Immutable identity |
| --- | --- |
| [`open_webui-0.11.0.tar.gz`](https://files.pythonhosted.org/packages/e1/09/3239c518cc7bd0582da021d4f12962399178ab3c833dc1832720cf2ff9f8/open_webui-0.11.0.tar.gz) | SHA-256 `e28c4fa997bf0a678caa7a0db6441da2e0c33b9a4120677f959ec3e45fccf9e9` |
| [`open_webui-0.11.0-py3-none-any.whl`](https://files.pythonhosted.org/packages/b0/63/87edc2cade790151d1595b05fbba1bde0c2df1fb2d0be80f2863667816e0/open_webui-0.11.0-py3-none-any.whl) | SHA-256 `71c266be87d0fb2cd79d9172d0e86a3b1b59d550d7054622b831344df07d361b` |
| [`pyproject.toml`](https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/pyproject.toml) | SHA-256 `179c9777983a4eaeff0032d8450d4a7fe2ddc4e744476ae3853d6bd6b61b8073` |
| [`uv.lock`](https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/uv.lock) | SHA-256 `bf42de5c836d5afe5628533cf8369e856d5d09bfd00efef302c31df3fa249947` |
| [`package.json`](https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/package.json) | SHA-256 `1cb9646a33d32e12dad52d166de6a5a04d9813c5d01250c05101cf4e4410b202` |
| [`package-lock.json`](https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/package-lock.json) | SHA-256 `664ff34f1d8273e2e6a7a6b6437d27fd195d289ea3df9c56cdd30c4afbd62b02` |
| [`hatch_build.py`](https://github.com/open-webui/open-webui/blob/f9590b8017199e56d5e953657e6498e3cef1d246/hatch_build.py) | SHA-256 `b65bde099c7c8be8433cc7998d86e6e32872857874c516764d0650846af0c1c8` |

The sdist is the code and frontend source. The wheel is a second immutable
source used only as the release-authored browser asset seed and comparison
oracle. It contains 60 files under `open_webui/frontend/pyodide`, totaling
59,832,549 bytes. A manifest formed from sorted lines of
`<sha256><two spaces><relative path><newline>` has SHA-256
`57b3bc90e6ebca23c0cec1736e470fbb2fee1c6b05531551b8871f3cbdab185c`.
G1 should extract only that directory into the source tree and verify the
manifest before running the frontend build.

The exact-version AUR package at
[`6a65fb1cc4583d1ab9a1215a9cdf74054b36655b`](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=open-webui&id=6a65fb1cc4583d1ab9a1215a9cdf74054b36655b)
is advisory only. It runs `uvx --python 3.11 open-webui@0.11.0` at runtime and
therefore does not provide an immutable pacman-owned application closure.

### RapidOCR successor

RapidOCR `v3.9.2` resolves to
[`095232a4c94f7f0e6600ba5bba1177010ad696d4`](https://github.com/RapidAI/RapidOCR/commit/095232a4c94f7f0e6600ba5bba1177010ad696d4).
PyPI publishes a wheel but no sdist, so the source package must build the
`python/` project from the immutable commit archive.

| Input | Immutable identity |
| --- | --- |
| [Commit archive](https://codeload.github.com/RapidAI/RapidOCR/tar.gz/095232a4c94f7f0e6600ba5bba1177010ad696d4) | SHA-256 `be524502995f5a2628b777daa6cf37d207aa7a6d9d3488c942338ff3698aef5f` |
| [`v3.9.2` tag archive](https://github.com/RapidAI/RapidOCR/archive/refs/tags/v3.9.2.tar.gz) | SHA-256 `0342bb616322661038eec54e6d14935a09e13fd0bcfecc7d8c3faf16e34fa805`; BLAKE2b-512 `cf5a1b6bd85802bb194777e58a53f20791713630226b76dcd22110c3155a97e6cc37f427a1e88907bd5ed49577bcf410a1b08bf048de7c0b39a97e423d3e6953` |
| [PyPI wheel](https://files.pythonhosted.org/packages/55/ed/0ee9b9281986974be9d2406ae0134c8d7c91d2fc613f16ffda9701eeda6f/rapidocr-3.9.2-py3-none-any.whl) | SHA-256 `04d6b8d151f823d930bd91910555f57bea897c0c44fa6794267b94cf9c1ef9a0` |

The release action runs
[`prepare_wheel_assets.py`](https://github.com/RapidAI/RapidOCR/blob/095232a4c94f7f0e6600ba5bba1177010ad696d4/python/tools/prepare_wheel_assets.py)
before building. The local package must reproduce that source-preparation step
with these exact default models:

| Packaged path | Immutable source | SHA-256 |
| --- | --- | --- |
| `rapidocr/models/PP-OCRv6_det_small.onnx` | [PP-OCRv6 detector](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv6/det/PP-OCRv6_det_small.onnx) | `090f04abcd9d9a7498bc4ebf677e4cb9bdce1fe4197ddb7e529f1ef44e1ff94f` |
| `rapidocr/models/ch_ppocr_mobile_v2.0_cls_mobile.onnx` | [PP-OCRv4 classifier](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv4/cls/ch_ppocr_mobile_v2.0_cls_mobile.onnx) | `e47acedf663230f8863ff1ab0e64dd2d82b838fceb5957146dab185a89d6215c` |
| `rapidocr/models/PP-OCRv6_rec_small.onnx` | [PP-OCRv6 recognizer](https://www.modelscope.cn/models/RapidAI/RapidOCR/resolve/v3.9.2/onnx/PP-OCRv6/rec/PP-OCRv6_rec_small.onnx) | `6f327246b50388f3c176ae304bd95767ea6dc0c9ae92153ef8cbe210b3c14884` |

Those hashes match the model files inside the PyPI wheel. Upstream's
[`config.yaml`](https://github.com/RapidAI/RapidOCR/blob/095232a4c94f7f0e6600ba5bba1177010ad696d4/python/rapidocr/config.yaml)
selects ONNX Runtime for detection, classification, and recognition and leaves
CUDA disabled. The package should hard-depend on the generic
`python-onnxruntime` provider and retain the packaged configuration under the
library root. It should not move this static library default into `/etc`.

The exact AUR recipe at
[`c2ed4f7f5844204ca6a110bd683c395fac3f406c`](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=python-rapidocr&id=c2ed4f7f5844204ca6a110bd683c395fac3f406c)
is the packaging reference. Local divergences are deliberate:

- make `python-onnxruntime` a hard dependency, not an optional backend;
- keep the upstream package-owned `config.yaml` location;
- package and verify all three models before build; and
- name the package `python-rapidocr`, with `conflicts` and `replaces` for
  `python-rapidocr-onnxruntime`, but do not `provide` the legacy package. The
  old package exposes a different import and API.

RapidOCR retains explicit model-download APIs upstream. G2 must run with empty
caches and blocked network and prove the default OCR path uses the packaged
models without calling them.

### Sentence Transformers

Sentence Transformers `v5.5.1` resolves to
[`ce3ec6d87f25b2d1cccb0a20f8fd495dad5c30fb`](https://github.com/huggingface/sentence-transformers/commit/ce3ec6d87f25b2d1cccb0a20f8fd495dad5c30fb).

| Input | Immutable identity |
| --- | --- |
| [GitHub tag archive](https://github.com/huggingface/sentence-transformers/archive/refs/tags/v5.5.1.tar.gz) | SHA-256 `8da8a135f5aca24c7b223307be7524d510d8a516a4d196124da82ee103060e16`; SHA-512 `8ee894f9910b29b0523f9abf5d6ebeb0cf8792a6cbc4efa8169002e59c085b1a2e82fa6225d6d9d9733eff394c1dc2620a39b5f35889db77265b6b028b411c45` |
| [PyPI sdist](https://files.pythonhosted.org/packages/cf/d4/7ef93157485e978c016f49da05363c1e4e7237beb5343b64b5631101f0f1/sentence_transformers-5.5.1.tar.gz) | SHA-256 `02b7740dfc60bdbbcb6061625f5d97a5c1a4e2d3baac5f9391b912bb5eae2290` |

The repo's existing recipe already matches the exact historical AUR recipe at
[`0e95caf85f392df2734f598b84f9562253b91869`](https://aur.archlinux.org/cgit/aur.git/tree/PKGBUILD?h=python-sentence-transformers&id=0e95caf85f392df2734f598b84f9562253b91869).
G1 should retain that source-build shape and rebuild it against the frozen
Python 3.14 providers. The package owns the library, not model weights. G2 must
use an explicitly staged local fixture for deterministic save/load and block
network access.

## Exact Python 3.14 and system-provider matrix

Generic dependency names remain in `depends`; the selected packages satisfy
them through `provides` where applicable. The speech rows are included because
the accepted provider tuple spans both lanes, but their recipes and tests
belong to the separate speech implementation.

| Runtime/import | Exact package selection | Owner | Intentional divergence |
| --- | --- | --- | --- |
| Python | `python-gfx1151` 3.14.6-1 | `arch-strix-halo-pkgs` | Upstream Open WebUI declares Python `<3.13`; local patch declares `<3.15` |
| Accelerate | `python-accelerate-gfx1151` 1.13.0-1 | `arch-strix-halo-pkgs` | Version matches upstream |
| NumPy | `python-numpy-gfx1151` 2.4.6-1 | `arch-strix-halo-pkgs` | System-owned |
| Pillow | `python-pillow-gfx1151` 12.2.0-1 | `arch-strix-halo-pkgs` | Version matches upstream |
| PyTorch | `python-pytorch-opt-rocm-gfx1151` 2.12.0-4 | `arch-strix-halo-pkgs` | System ROCm provider |
| SentencePiece | `python-sentencepiece-gfx1151` 0.2.1-2 | `arch-strix-halo-pkgs` | Version matches upstream |
| Tokenizers | `python-tokenizers-gfx1151` 0.22.2-1 | `arch-strix-halo-pkgs` | System-owned |
| Transformers | `python-transformers-gfx1151` 5.8.1-1 | `arch-strix-halo-pkgs` | Upstream pins 5.5.4 |
| ONNX Runtime | `python-onnxruntime-opt-rocm` 1.28.0-1, providing `python-onnxruntime` | Arch | Upstream pins 1.26.0; RapidOCR sessions must select `CPUExecutionProvider` |
| OpenCV | `opencv` 5.0.0-9.1 | CachyOS/Arch provider | Upstream pins `opencv-python-headless` 4.13.0.92 |
| pandas | `python-pandas` 2.3.3-2.1 | CachyOS/Arch provider | Upstream pins 3.0.3 |
| PyArrow | `python-pyarrow` 24.0.0-1.1 | CachyOS/Arch provider | Upstream pins 20.0.0 |
| SciPy | `python-scipy` 1.18.0-1.1 | CachyOS/Arch provider | System-owned |
| scikit-learn | `python-scikit-learn` 1.9.0-2 | Arch | System-owned |
| PyClipper | `python-pyclipper` 1.4.0-2.1 | CachyOS/Arch provider | System-owned |
| Shapely | `python-shapely` 2.1.2-2.1 | CachyOS/Arch provider | System-owned |
| RapidOCR | new `python-rapidocr` 3.9.2-1 | this repo | Replaces the legacy 1.4.4 package and import |
| Sentence Transformers | `python-sentence-transformers` 5.5.1-1 | this repo | Exact accepted target; later upstream versions are out of scope |
| PyAV | `python-av` 18.0.0-2.1 | speech/system lane | The live installation has moved to 18.1.0; G0 must select the retained 18.0.0 artifact or reopen the accepted version |
| CTranslate2 | `ctranslate2-gfx1151` plus Python bindings 4.8.1 | speech lane | The observed installed/provider baseline is still 4.7.2 |
| Faster Whisper | `python-faster-whisper` 1.2.1 | speech lane | Exact upstream Open WebUI pin |

The public source recipes for the gfx1151 subset are frozen by
[`arch-strix-halo-pkgs@a3f88a145bb9b69043cd4f99ef3673caf23b5869`](https://github.com/nisavid/arch-strix-halo-pkgs/commit/a3f88a145bb9b69043cd4f99ef3673caf23b5869).

| Recipe | Immutable upstream input |
| --- | --- |
| `python-gfx1151` 3.14.6 | Python source SHA-256 `143b1dddefaec3bd2e21e3b839b34a2b7fb9842272883c576420d605e9f30c63` |
| `python-accelerate-gfx1151` 1.13.0 | sdist SHA-256 `d631b4e0f5b3de4aff2d7e9e6857d164810dfc3237d54d017f075122d057b236` |
| `python-numpy-gfx1151` 2.4.6 | sdist SHA-256 `f3a3570c4a2a16746ac2c31a7c7c7b0c186b95ce902e33db6f28094ed7387dda` |
| `python-pillow-gfx1151` 12.2.0 | sdist SHA-256 `a830b1a40919539d07806aa58e1b114df53ddd43213d9c8b75847eee6c0182b5` |
| `python-pytorch-opt-rocm-gfx1151` 2.12.0 | ROCm/PyTorch commit `c7badbdf3d33d945a0ed4536aac5303bc933e6ee`; the immutable recipe records all nine patch hashes |
| `python-sentencepiece-gfx1151` 0.2.1 | sdist SHA-256 `8138cec27c2f2282f4a34d9a016e3374cd40e5c6e9cb335063db66a0a3b71fad`; patch SHA-256 `04b134d04727093b49455d44126988d104ea7019bbe6c72b7e2f8ddeb3686bb1` |
| `python-tokenizers-gfx1151` 0.22.2 | sdist SHA-256 `473b83b915e547aa366d1eee11806deaf419e17be16310ac0a14077f1e28f917` |
| `python-transformers-gfx1151` 5.8.1 | sdist SHA-256 `4dd5b6de4105725104d84fd6abd74b305f4debfc251b38c648ee5dd087cf543b` |

### Recoverable package artifacts

The following exact archives were present during the research audit. Record
their basenames and hashes in the G0 deployment manifest, copy them into a
controlled staging repository, and verify the copy byte-for-byte. The official
and CachyOS-origin archives also had detached signatures; the locally built
gfx1151 and Sentence Transformers archives did not.

| Archive basename | SHA-256 |
| --- | --- |
| `python-gfx1151-3.14.6-1-x86_64.pkg.tar.zst` | `0b3a5c1c1e29642fa75fe73f4a4097aa2cb38f948b58e62c340789bd6b2abe54` |
| `python-accelerate-gfx1151-1.13.0-1-any.pkg.tar.zst` | `7dbb80b1ccc2c68eb15fa3d1bf5401f7759ac8b60f24a34610c8743490b3c470` |
| `python-numpy-gfx1151-2.4.6-1-x86_64.pkg.tar.zst` | `7a5116bf6d43005f90a17e669e1952b963e369e62afa2c8a0bd6a1c68770e035` |
| `python-pillow-gfx1151-12.2.0-1-x86_64.pkg.tar.zst` | `3e4f975787b7e4176cca5671c731930f5556ef90f5b1a67e25c5f1ae2a08bf26` |
| `python-pytorch-opt-rocm-gfx1151-2.12.0-4-x86_64.pkg.tar.zst` | `cd25a8ce4b6e98fdcee84d2568c0a9e50ac6c50e17d3f695384231b938e65715` |
| `python-sentencepiece-gfx1151-0.2.1-2-x86_64.pkg.tar.zst` | `c2ad398d2624e42d3d6ac757afd311b5c50d79504bafda0ae6f41d1bf97423f6` |
| `python-tokenizers-gfx1151-0.22.2-1-x86_64.pkg.tar.zst` | `d1e7536826145bcfcf3ad07cdcfbeccf525a9bdc7d4da23471d992dbe15d4918` |
| `python-transformers-gfx1151-5.8.1-1-any.pkg.tar.zst` | `c5a3ab8ae6aef968fcd97b08eaf893ccd5eed0525102873ec86cc68c265f4518` |
| `python-onnxruntime-opt-rocm-1.28.0-1-x86_64.pkg.tar.zst` | `3f53eecb8042c678f5e46f15568d8570fa8ef28c320333aa902b88750496f996` |
| `opencv-5.0.0-9.1-x86_64_v4.pkg.tar.zst` | `c9f053d56e9028b598b427b6308fb4300bd6a41d6adc42aacf089f9d191edca7` |
| `python-pandas-2.3.3-2.1-x86_64_v4.pkg.tar.zst` | `b363f8a85093a34af0115ad3ce6e8303245a54fdfca4647db9e51385ed634996` |
| `python-pyarrow-24.0.0-1.1-x86_64_v4.pkg.tar.zst` | `d87b78c3ab22491e1b7af9f648ddce4b6a4adf0677edce92ce5b10d127902fdc` |
| `python-scipy-1.18.0-1.1-x86_64_v4.pkg.tar.zst` | `eb3021da8b89b3124fc60f32518bbc8a814ba20a5d1d955447647f2c72a2f1ec` |
| `python-scikit-learn-1.9.0-2-x86_64.pkg.tar.zst` | `ea72280f2bf597cd6076d6c552ab6b50b17a1a824d61874325c45eec69b51082` |
| `python-pyclipper-1.4.0-2.1-x86_64_v4.pkg.tar.zst` | `4baed390506a2be036905f689a5d26081dc4c6f50d125af2a125020c259dd18f` |
| `python-shapely-2.1.2-2.1-x86_64_v4.pkg.tar.zst` | `4c67dbce1f8c2ac3bda593708c5fb0e384183ea1bd42839afaff731aa076ed27` |
| `python-sentence-transformers-5.5.1-1-any.pkg.tar.zst` | `ae099f3496e02e1e17f5d3f6a93b11ba9f1e8d980377fb35b9f8e5552e732d0f` |
| `python-av-18.0.0-2.1-x86_64_v4.pkg.tar.zst` | `14a8a65211520c587fb4947939c36e249a58cc5581fc778358373594756aafeb` |

These are recovery inputs, not proof that G1 has rebuilt the three repo-owned
application packages or that G2 has accepted the installed runtime.

## Private non-system closure

The Open WebUI base dependency closure was recomputed against Python 3.14 on
`x86_64-unknown-linux-gnu` with `uv` 0.12.5 and source cutoff
`2026-08-18T06:25:20Z`. The scratch-only Python constraint changed upstream's
`>=3.11,<3.13.0a1` to `>=3.11,<3.15.0a1`. Versions came from the release's
immutable `uv.lock`; the resolution did not accept newer live-index versions.

The 21 excluded system distributions were:

```text
accelerate
av
ctranslate2
faster-whisper
numpy
onnxruntime
opencv-python
opencv-python-headless
pandas
pillow
pyarrow
pyclipper
rapidocr
scikit-learn
scipy
sentence-transformers
sentencepiece
shapely
tokenizers
torch
transformers
```

That exclusion list has SHA-256
`fdf91cf245d0f5050229b5ea8ef4067c997f79f012e06a16b18e740981b395a3`.
The exact 220-name constraint set below has SHA-256
`35c42885a5eaff845291bec450667c588d51acba3b88227e2a9f19e6f5dd7fb1`.
The generated `--generate-hashes --no-header --no-annotate` lock has SHA-256
`7ad581f712aa55f016ed1c18da5b854d5eef99b4878beb6aec21dfe4587f8573`.
It had zero name overlap with the exclusions.

G0 must commit the full generated hash lock as a package source; this research
file records the exact answer and audit digest, but the digest alone is not a
deployable lock. G1 should install this lock into `/opt/open-webui`, then install
the locally built Open WebUI wheel with dependency resolution disabled.

```text
aiocache==0.12.3
aiodns==4.0.4
aiofiles==25.1.0
aiohappyeyeballs==2.6.2
aiohttp==3.13.5
aiosignal==1.4.0
aiosqlite==0.22.1
alembic==1.18.4
annotated-doc==0.0.4
annotated-types==0.7.0
anthropic==0.86.0
anyio==4.14.0
apscheduler==3.11.2
argon2-cffi==25.1.0
argon2-cffi-bindings==25.1.0
asgiref==3.11.1
async-timeout==5.0.1
attrs==26.1.0
authlib==1.7.2
azure-ai-documentintelligence==1.0.2
azure-core==1.41.0
azure-identity==1.25.3
azure-storage-blob==12.29.0
bcrypt==5.0.0
beautifulsoup4==4.14.3
bidict==0.23.1
black==26.5.1
boto3==1.42.62
botocore==1.42.97
brotli==1.2.0
brotlicffi==1.2.0.1
build==1.5.0
certifi==2026.6.17
cffi==2.0.0
chardet==7.4.3
charset-normalizer==3.4.7
chromadb==1.5.9
click==8.4.1
cryptography==48.0.0
ddgs==9.14.4
defusedxml==0.7.1
distro==1.9.0
docstring-parser==0.18.0
docx2txt==0.9
durationpy==0.10
einops==0.8.2
et-xmlfile==2.0.0
events==0.5
fake-useragent==2.2.0
fastapi==0.136.3
fonttools==4.63.0
fpdf2==2.8.7
frozenlist==1.8.0
ftfy==6.3.1
google-api-core==2.31.0
google-api-python-client==2.197.0
google-auth==2.55.0
google-auth-httplib2==0.4.0
google-auth-oauthlib==1.4.0
google-cloud-core==2.6.0
google-cloud-storage==3.9.0
google-crc32c==1.8.0
google-genai==1.66.0
google-resumable-media==2.10.0
googleapis-common-protos==1.75.0
greenlet==3.5.2
grpcio==1.78.0
h11==0.16.0
h2==4.3.0
hiredis==3.4.0
hpack==4.1.0
httpcore==1.0.9
httplib2==0.31.2
httptools==0.8.0
httpx==0.28.1
httpx-sse==0.4.3
hyperframe==6.1.0
idna==3.18
importlib-resources==7.1.0
isodate==0.7.2
itsdangerous==2.2.0
jiter==0.15.0
jmespath==1.1.0
joblib==1.5.3
joserfc==1.7.4
jsonpatch==1.33
jsonpointer==3.1.1
jsonschema==4.26.0
jsonschema-specifications==2025.9.1
kubernetes==36.0.2
langchain==1.2.10
langchain-classic==1.0.7
langchain-community==0.4.2
langchain-core==1.4.8
langchain-protocol==0.0.18
langchain-text-splitters==1.1.2
langgraph==1.0.10
langgraph-checkpoint==4.1.1
langgraph-prebuilt==1.0.13
langgraph-sdk==0.3.15
langsmith==0.8.18
ldap3==2.9.1
loguru==0.7.3
lxml==6.1.1
mako==1.3.12
markdown==3.10.2
markdown-it-py==4.2.0
markupsafe==3.0.3
mcp==1.27.2
mdurl==0.1.2
mmh3==5.2.1
msal==1.37.0
msal-extensions==1.3.1
msoffcrypto-tool==6.0.0
multidict==6.7.1
mypy-extensions==1.1.0
nltk==3.9.4
oauthlib==3.3.1
olefile==0.47
openai==2.29.0
openpyxl==3.1.5
opensearch-protobufs==1.2.0
opensearch-py==3.2.0
opentelemetry-api==1.42.1
opentelemetry-exporter-otlp-proto-common==1.42.1
opentelemetry-exporter-otlp-proto-grpc==1.42.1
opentelemetry-proto==1.42.1
opentelemetry-sdk==1.42.1
opentelemetry-semantic-conventions==0.63b1
orjson==3.11.9
ormsgpack==1.12.2
overrides==7.7.0
packaging==26.2
pathspec==1.1.1
platformdirs==4.10.0
primp==1.3.1
propcache==0.5.2
proto-plus==1.28.0
protobuf==6.33.6
psutil==7.2.2
psycopg==3.3.4
psycopg-binary==3.3.4
pyasn1==0.6.3
pyasn1-modules==0.4.2
pybase64==1.4.3
pycares==5.0.1
pycparser==3.0
pycrdt==0.13.1
pydantic==2.13.4
pydantic-core==2.46.4
pydantic-settings==2.14.2
pydub==0.25.1
pygments==2.20.0
pyjwt==2.13.0
pymdown-extensions==10.21.3
pymysql==1.2.0
pypandoc==1.17
pyparsing==3.3.2
pypdf==6.7.5
pypika==0.51.1
pyproject-hooks==1.2.0
python-dateutil==2.9.0.post0
python-dotenv==1.2.2
python-engineio==4.13.2
python-mimeparse==2.0.0
python-multipart==0.0.32
python-pptx==1.0.2
python-socketio==5.16.2
pytokens==0.4.1
pytube==15.0.0
pytz==2026.2
pyxlsb==1.0.10
pyyaml==6.0.3
rank-bm25==0.2.2
redis==8.0.1
referencing==0.37.0
regex==2026.5.9
requests==2.34.2
requests-oauthlib==2.0.0
requests-toolbelt==1.0.0
restrictedpython==8.2
rich==13.9.4
rpds-py==2026.5.1
s3transfer==0.16.1
shellingham==1.5.4
simple-websocket==1.1.0
six==1.17.0
sniffio==1.3.1
socksio==1.0.0
soundfile==0.13.1
soupsieve==2.8.4
sqlalchemy==2.0.50
sse-starlette==3.4.4
starlette==1.3.1
starlette-compress==1.7.1
starsessions==2.2.1
tenacity==9.1.4
tiktoken==0.13.0
tqdm==4.68.3
typer==0.25.1
typing-extensions==4.15.0
typing-inspection==0.4.2
tzlocal==5.4.3
uritemplate==4.2.0
urllib3==2.7.0
uuid-utils==0.16.2
uvicorn==0.51.0
uvloop==0.22.1
validators==0.35.0
watchfiles==1.2.0
wcwidth==0.8.1
websocket-client==1.9.0
websockets==16.0
wsproto==1.3.2
xlrd==2.0.2
xlsxwriter==3.2.9
xxhash==3.7.0
yarl==1.24.2
youtube-transcript-api==1.2.4
zstandard==0.25.0
```

Some private packages, including `huggingface-hub`, `safetensors`, `psutil`,
and `pyyaml`, are also installed transitively by system provider packages.
They remain in the private non-system closure and may be preferred by
Open WebUI's explicit private-path ordering. This is intentional. The payload
denylist applies only to the 21 externalized distributions above.

## Build shape and package boundaries

### Open WebUI build

Upstream's custom Hatch hook runs `npm install --force` and then
`npm run build`. The latter runs `pyodide:fetch` before Vite. The fetch script
loads packages from the network and resolves four PyPI packages from their
latest release at build time. Neither behavior is an acceptable immutable
source boundary.

G1 should instead:

1. use Node 22, which satisfies upstream's `>=18.13.0 <=22.x.x` engine range;
2. patch the Hatch hook to run `npm ci` against the frozen
   `package-lock.json` without changing it;
3. seed and verify `static/pyodide` from the exact release wheel described
   above;
4. have that same hook invoke Vite directly, without `pyodide:fetch`, so the
   normal Python wheel build performs exactly one frontend build;
5. build the Python wheel from the sdist with the re-derived Python 3.14,
   system-provider, and offline-frontend patches; and
6. install the committed private hash lock followed by the local application
   wheel with dependency resolution disabled.

Retain the existing packaging controls that disable the Cypress binary fetch,
skip ONNX Runtime Node CUDA installation, ignore a global libvips, isolate npm
and `uv` caches, and record the exact Node and npm versions in build evidence.

The Python compatibility patch must change only the Python upper bound to
`<3.15.0a1`. It must not carry the old Pydantic or Psycopg substitutions. The
system-provider patch removes the 21 distributions listed above and applies
the accepted PyArrow 24 and provider-version divergences.

### Payload ownership

| Payload | Owning package/lane | Required audit |
| --- | --- | --- |
| Open WebUI Python modules, frontend, private non-system closure, launcher, service assets, and configuration defaults | `open-webui` | Every file is in the package manifest; no startup package manager or bootstrap |
| Browser Pyodide wheels, WebAssembly, and worker assets under the compiled frontend | `open-webui` | Preserve the frozen 60-file seed; do not compare it with server site-package roots |
| `rapidocr`, its metadata and console entry, config, and three default ONNX models | `python-rapidocr` | Default OCR works with empty caches and no network |
| `sentence_transformers` and its distribution metadata | `python-sentence-transformers` | No model weights in the package; offline tests use a staged fixture |
| The 21 externalized server distributions, their import roots, native libraries, distribution metadata, and console entries | their pacman provider packages | None may remain under `/opt/open-webui`; each imported file resolves through `pacman -Qo` |
| Python/gfx provider recipes and rebuilt artifacts | `arch-strix-halo-pkgs` | Exact recipe commit plus retained/rebuilt archive hash |
| CTranslate2, Faster Whisper, and PyAV acceptance | speech lane | Separate build and offline runtime tests; exact versions still participate in household promotion |

The denylist must be derived from the 21 distribution records, not from a
hand-maintained subset of import directories. For each distribution, inspect
its wheel metadata or installed `RECORD` and reject all matching server-side
module roots, `.dist-info`, `.data`, native-library directories, and console
entries under `/opt/open-webui`. The check must fail if a new upstream artifact
shape appears. Post-install deletion without a final assertion is insufficient.

## G0-G2 route and deployable artifacts

| Gate | Required work | Artifact/deployment result |
| --- | --- | --- |
| G0: freeze | Add immutable source URLs and hashes, commit the full private hash lock, regenerate `.SRCINFO`, record provider archive hashes/signatures, and copy or rebuild missing provider archives into a controlled staging repository | A complete input and recovery manifest. No new application package is deployable yet. |
| G1: build | Build `python-rapidocr` 3.9.2, rebuild `python-sentence-transformers` 5.5.1, build Open WebUI 0.11.0 from source with the frozen frontend assets, inspect payloads, and pass the externalization denylist | Three exact pacman archives become deployable to a staging repository. Stage them together with the G0 provider set and record repository database plus package hashes as part of G1. Do not promote to the household repository yet. |
| G2: core runtime | Install the entire exact set from that staging repository and pass offline RapidOCR, Sentence Transformers fixture save/load, Open WebUI import/version, CPUExecutionProvider, negative-network, and `pacman -Qo` checks | The core package set becomes a promotion candidate. Promote the exact staging database and archives only after G2; household service activation still waits for G3 and G4. |

This staging and promotion work belongs inside the applicable gate, not in an
untracked follow-up. G1 is incomplete without repository staging and immutable
artifact identities. G2 is incomplete without installing those identities and
recording the exact promoted candidate.

## Open decisions and routing

- G0 must preserve the recovery archives before cache cleanup or repository
  drift makes them unavailable. Rebuilding from the immutable recipes is an
  acceptable fallback, but the rebuilt archive gets a new recorded identity
  and must pass the same G2 tests.
- The accepted PyAV version is 18.0.0, while the live installed provider is
  18.1.0. The retained `18.0.0-2.1` archive makes the accepted route possible.
  If the speech lane prefers 18.1.0, it must explicitly reopen that version
  decision instead of drifting silently.
- CTranslate2 4.8.1 remains a speech-lane deliverable. The core package closure
  must not claim the full household provider tuple until that lane closes.
- The current repo recipe still targets Open WebUI 0.9.5 and legacy
  `python-rapidocr-onnxruntime` 1.4.4. They are implementation inputs, not
  accepted package baselines.

With those routes recorded, issue #63's research question is decision-complete.
The implementation owner can cite this artifact in G0 and close #63 without
changing package files in the research branch.
