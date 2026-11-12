# Train your own model (Phase 3B)

Folders you create yourself (do NOT put them inside `dataset/` - the script builds that):
```
raw_genuine/        <- your REAL medicine-pack photos (jpg/png). Name them like  paracetamol_001.jpg, paracetamol_002.jpg
raw_counterfeit/    <- OPTIONAL: real counterfeit photos (only if you really have them)
```
Minimum: ~300 genuine photos (more is better; 1000+ ideal). Take photos at different angles, lights, backgrounds.

## A) On Google Colab (recommended, free GPU)
1. colab.research.google.com -> Runtime -> Change runtime type -> **T4 GPU**
2. Upload `medsecure_ai.zip` and your `raw_genuine` folder (zip it too), then:
```
!unzip -q medsecure_ai.zip
%cd medsecure_ai
!unzip -q ../raw_genuine.zip -d ../raw_genuine
!pip install -q opencv-python-headless pillow
!python training/prepare_dataset.py --genuine ../raw_genuine --simulate-counterfeit --group-by-prefix
!python training/train_model.py --epochs 8 --fine-tune-epochs 6
```
3. Download the 4 files from `trained_model/` and put them in your local `trained_model/` folder.

## B) On your laptop (slower, CPU)
```
python training/prepare_dataset.py --genuine raw_genuine --simulate-counterfeit --group-by-prefix
python training/train_model.py --epochs 5 --fine-tune-epochs 3 --batch 16
python check_model.py
python app.py
```
First run downloads ImageNet weights (needs internet). `--no-pretrained` is only for quick offline tests.

## Output files (put in `trained_model/`)
`medicine_classifier.keras`, `class_indices.json`, `model_meta.json`, `training_report.json`
Read `training_report.json` for real test accuracy, confusion matrix, per-class precision/recall.

---
# Reaching 100,000+ images (recommended plan)

## Step 1: download NIH pill images (real photos, resized while downloading, ~1-2 GB for 100k)
```
python training/download_nih_pills.py --out raw_nih_pills --count 100000 --size 256 --workers 8
```
Takes a long time (300 images took ~1 min on Colab, so 100,000 is roughly 4-6 hours; the new version decodes faster). Safe to stop with Ctrl+C and run again, it resumes.
Do it on Colab if your internet is slow. NIH lists 120,937 images; to keep 100,000+ after filtering use `--count 121000`.
File names become `D017_<random id>.jpg` (disc number first), used by `--group-by-prefix`.

## Step 2: build the dataset (quality filter, duplicate removal, leakage-free split)
```
python training/prepare_dataset.py --genuine raw_nih_pills --simulate-counterfeit --group-by-prefix --save-size 224
```
It prints `TOTAL usable images`. That is your real, verified count (also saved in `dataset/DATASET_INFO.json`).
Disk: ~200k small JPEGs. Colab or a laptop with 10+ GB free is fine.

## Step 3: stage-1 training on pills
```
python training/train_model.py --epochs 6 --fine-tune-epochs 4 --batch 64 --out trained_model_pills
```
Use a GPU (Colab T4). On a CPU laptop this is too slow, reduce with `--max-genuine 20000` in step 2.

## Step 4: stage-2 on your PACK photos (this is what makes the app work on packaging)
```
python training/prepare_dataset.py --genuine raw_packs --simulate-counterfeit --group-by-prefix --save-size 224
python training/train_model.py --init-from trained_model_pills/medicine_classifier.keras --fine-tune-epochs 5 --batch 32
```
`raw_packs/` = your own pack photos + Roboflow packaging datasets (see `dataset/DATASETS.md`).
Result files go to `trained_model/`. Then: `python check_model.py` and `python app.py`.

---
# Option C: 1,00,000+ PACKAGE images with QR + barcode (synthetic, fastest way to reach 1L)
```
pip install qrcode pillow numpy opencv-python-headless
python training/generate_synthetic_packs.py --count 120000 --workers 8
python training/train_model.py --epochs 6 --fine-tune-epochs 4 --batch 64
```
Writes straight into `dataset/{train,validation,test}/{genuine,counterfeit}` + `labels.csv` + `DATASET_INFO.json`.
Speed: about 24 images/sec on 4 cores (120k = roughly 1.5 hours; use Colab or run overnight).
Genuine = valid EAN-13 + matching QR. Counterfeit = SIMULATED defects (bad check digit, QR missing/mismatch, blur,
colour shift, typo, wrong date format, no hologram). Split is by product, so no leakage.
Say clearly in the report: synthetic proof-of-concept; fine-tune on real pack photos (stage 2 above) for the honest accuracy.
