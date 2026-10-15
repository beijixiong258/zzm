# Parser 集成：parent 安装手册（未部署）

## 已完成与边界

- 应用 `source_identity` 对 PNG/APNG/WebP 全部 display frames（含 APNG default/poster）进行格式、数量、尺寸、校验和像素解码；返回完整帧数。保持 64MiB / 1000frames / 每帧16MP；原文件不改。JPEG 同时要求真实像素解码。
- 精确 release allowlist 增加 `tools/material_stage13/ocr_verification.py`。仅做64个Python运行模块的 scoped snapshot/import/native smoke，**没有构建最终release**。
- installed r4 仍是旧 immutable parser。这里没有安装新parser、修改installed venv/root目录、GPU请求、sudo或生产配置。

## 已准备的离线payload

Ubuntu：`/home/adminz/llm/ocr-stage1-20261009/stage14-parser-integration/`

- `dependency-manifest.json`：4个wheel与3个原有ONNX的size/SHA256；`requirements-offline.txt`：精确版本和pip哈希要求。
- `wheels/`：RapidOCR3.9.2、OmegaConf2.4.0、colorlog6.12.0、opencv-python5.0.0.93。由于公共pip下载超时，改为从baseline已安装wheel的**原RECORD逐文件核验后repack**；这些是本次生成的wheel哈希，不是publisher下载哈希。保留package native libs/许可证/元数据；不是整venv拷贝。
- `models/`：baseline既有 `PP-OCRv6_det_small.onnx`、`PP-OCRv6_rec_small.onnx`、`ch_ppocr_mobile_v2.0_cls_mobile.onnx`，原件与staging SHA相同。没有下载新权重。
- 总payload **130352324 bytes**（4wheel+3独立权重；wheel本身也包含baseline原已打包的同款weights）。
- `overlay/`：只在本lane staging内使用pip离线安装4wheel，installed解释器以PYTHONPATH加载该overlay；installed site-packages未变。
- `code/dependency_install.py`：默认只读plan；仅parent root helper可显式 `--install`。
- `code/cpu_install_check.py`：真实CPU OCR smoke，网络requests被阻断，CPU provider实查，`--expected-uid 999`强制最终账号。

## 已验证CPU兼容性；还缺最终账号安装验收

使用 `/opt/aicademiya-documents/runtime/.venv/bin/python` + isolated overlay，UID1000：

- 三真实ONNX sessions仅 `CPUExecutionProvider`；合成3行groundtruth逐字一致，零GPU/服务请求。
- RapidOCR及必要dependency closure完整；overlay `pip check` 返回 `No broken requirements found`。
- OpenCV `ldd` 配合原有native-libs目录，零 `not found`。
- 复用installed ONNX Runtime1.31.0、NumPy2.5.3、Pillow12.3.0及其他现有依赖，不替换成baseline旧版本；OmegaConf2.4.0已vendor ANTLR，无需另加antlr wheel。

**installed环境原本缺RapidOCR、cv2、OmegaConf、colorlog。UID999尚未安装/执行；上述结果不是UID999通过，更不是全材料OCR/图表语义通过。**

## Parent executable recipe

先通过可信本地 `artifacts/stage14/parser-integration/dependency-readback.json` 核对 remote manifest/script SHA；不要把payload hash当签名。root helper执行下面命令前应先完成parent的安装时机/备份判断。本lane只实际执行了无 `--install` 的plan。

```sh
P=/home/adminz/llm/ocr-stage1-20261009/stage14-parser-integration
V=/opt/aicademiya-documents/runtime/.venv
M=/opt/aicademiya-documents/shared/rapidocr-models-stage14

# Read-only preflight: precise payload hashes + unchanged installed dependencies.
"$V/bin/python" -B "$P/code/dependency_install.py" \
  --payload "$P" --venv "$V" --models-target "$M"

# PARENT root helper only: four wheels, no-index/no-deps/require-hashes;
# creates ONLY the new M directory with root-owned0644 weights/0755 dir.
"$V/bin/python" -B "$P/code/dependency_install.py" \
  --payload "$P" --venv "$V" --models-target "$M" --install

# Run the CURRENT NEW packaged parser, not installed oldr4/code aliases.
# Parent supplies the exact new release path and writes the worker-account report
# to its own approved writable QA location. UID999 identity is derived, not guessed.
WORKER_USER=$(/usr/bin/python3 -c 'import pwd;print(pwd.getpwuid(999).pw_name)')
PARSER_DIR=/opt/aicademiya-documents/releases/PARENT_NEW_RELEASE/tools/material_stage13
runuser -u "$WORKER_USER" -- env \
  CUDA_VISIBLE_DEVICES= PYTHONDONTWRITEBYTECODE=1 \
  LD_LIBRARY_PATH=/opt/aicademiya-documents/shared/native-libs/usr/lib/x86_64-linux-gnu \
  "$V/bin/python" -B "$P/code/cpu_install_check.py" \
  --expected-uid 999 --models "$M" --parser-dir "$PARSER_DIR"
```

`M`必须不存在，否则plan拒绝；依赖若与已检查版本有drift则拒绝并要求重新inspect，不升级或覆盖共享libs。默认roothelper对installed venv仅补4个明确缺包；安装后pip check和三权重size/hash读取必须成功。模型选择由parent明确接入 `--ocr-models "$M"` / `AICADEMIYA_RAPIDOCR_MODELS`；本lane没有修改supervisor/env/installer。最终installed UID999 smoke、actual app→restricted worker、新parserGPU recovery及semantic gates由parent完成。

## 本地实测证据

详见同目录 `verification-summary.json` 和各XML/JSON/log。所有app fixtures均为synthetic隔离数据；CPU groundtruth是真实ONNX inference，不是伪造服务response。初次Linux harness误把CLI脚本当pytest收集，及snapshot换行比较错误的失败证据保留，随后只修harness、未放松产品检查。
