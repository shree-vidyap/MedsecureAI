# MedSecure AI - Dataset Report (verified on 2 Oct 2026)

**Summary:** A verified public source with **about 133,000 real medicine-related images** exists: the NIH NLM **C3PI** consumer-grade
pill image collection. That alone covers the 100,000+ requirement. BUT these are **pill photos** (not packaging) and they have
**no genuine/counterfeit labels**. No large public dataset with REAL counterfeit labels was found. See section E for the honest way to use them.

## A. Verified medicine-related datasets

| # | Dataset | Source / URL | Images | Classes / labels | Image type | License | Academic use | Download |
|---|---------|--------------|--------|------------------|------------|---------|--------------|----------|
| 0 | **NIH NLM C3PI (RxIMAGE) - consumer-grade images** | https://data.lhncbc.nlm.nih.gov/public/Pills/index.html (110 folders `PillProjectDisc1..110`) | **120,937 files listed in NLM's own file list** (catalog text says ~133,000; I could only confirm 120,937, checked 2 Oct 2026 by running the downloader) | prescription pill types; product code is in the file name; no authenticity labels | Pills, real consumer-style photos | US National Library of Medicine; "images and metadata for research and development purposes only" | Yes (research) | Yes, direct HTTP download (project was sunset in 2018 but files were still online on 2 Oct 2026) |
| 1 | ePillID | https://github.com/usuyama/ePillID-benchmark | 13,532 (9,804 reference + 3,728 consumer) | 4,902 pill types / 9,804 appearance classes | Pills, controlled + real-world photos | Repo: MIT. Data derived from NIH NLM public data. "Released for research purposes only" | Yes (research) | GitHub Releases page |
| 2 | Drug Name Detection Dataset | https://gts.ai/dataset-download/the-drug-name-detection-dataset/ | 1,823 | Drug-name label boxes (detection) | Bottles, blister packs, vials, packs | CC0 (per listing; original source not verified) | Yes (CC0) | Yes |
| 3 | OCR Lot Code and Expiry Date (Roboflow) | https://blog.roboflow.com/ocr-lot-code-and-expiry-date-verification/ | 1,716 | `name`, `date` (batch + expiry strip) | Pharmaceutical boxes | NOT verified - check on Roboflow Universe page | Check licence | Roboflow account |
| 4 | Boxes medicine 2 (Roboflow) | https://universe.roboflow.com/marianaramirezsanchez/boxes-medicine-2 | count NOT verified | drug_name_region, expiration_date_region, formula, medicine_bottle, medicine_box | Medicine boxes/bottles | CC BY 4.0 | Yes (cite author) | Roboflow account |
| 5 | Ultralytics medical-pills | https://docs.ultralytics.com/datasets/detect/medical-pills | count NOT verified (small proof-of-concept set) | pill detection | Pills | AGPL-3.0 | Yes (AGPL terms) | Yes |

**Counting without cheating:**
- Row 0 (120,937 listed) is the only source big enough alone. Filtering (blur / duplicates) removes some, so download ALL of it (`--count 121000`) if you need 100,000+ REAL images after filtering.
- ePillID (row 1) is built FROM the NIH challenge + Pillbox data, so it **overlaps row 0. Do NOT add it to the total.**
- Rows 2-3 (1,823 + 1,716 = 3,539) are real packaging photos, small but most relevant to your app.
- Rows 4-5: size not verified, not counted.
- **Your final number = the `total_images` value written by `prepare_dataset.py` in `dataset/DATASET_INFO.json`** (real, computed after filtering and duplicate removal). Quote that, not a guess.
- Note: one 2026 paper's comparison table lists the NIH consumer images as "not publicly available", but the NLM download page was online and listing the files when I checked. Download early and keep a copy.

## B. Datasets for QR / barcode detection (not medicine specific)
| Dataset | Source | Images | Licence |
|---|---|---|---|
| Barcode + QR custom dataset (Kaggle, used in YOLOv8 study arXiv:2511.22937) | Kaggle (link in the paper) | 31,078 | NOT verified |
| Barcode/QR dataset list (many CC BY 4.0) | https://github.com/BenSouchet/barcode-datasets | varies | per dataset - check each |

You do NOT need to train anything for QR/barcode: the browser BarcodeDetector / jsQR / OpenCV decoders already work.

## C. OCR (batch, expiry, manufacturer)
Tesseract is pre-trained. You do not need a training dataset for it. Rows 2-4 are useful only to TEST your OCR accuracy.

## D. Real counterfeit images - the real problem
- Real counterfeit pack photos are not openly published at scale.
- A Nigerian study used only a few fake-pack samples obtained from NAFDAC (the national regulator); other fake samples were created artificially.
- An IIT Kanpur proposal suggests requesting seized counterfeit samples through the District Drug Inspector / State Drugs Control Department.
- Ask your college guide to write to your local Drugs Control office or a pharmacy association.

## E. How to use these WITHOUT falsely labelling anything as counterfeit
1. **Never** put normal medicine photos in `counterfeit/`.
2. `genuine/` = real pack photos (your own photos of real packs from a licensed pharmacy + rows 2-4). Authenticity is not independently verified, say so.
3. `counterfeit/` = (a) REAL counterfeit photos if you can get them, and/or (b) **simulated** altered copies made by
   `training/prepare_dataset.py --simulate-counterfeit`. They are recorded as `simulated` in `DATASET_INFO.json`,
   `model_meta.json`, and the Result page shows a "Proof-of-concept model" note.
4. A model trained only on simulated fakes learns the simulation artefacts, NOT real counterfeit detection. Report test accuracy as such.
5. **Pills vs packs:** NIH images are pills, but your app analyses packaging. A model trained only on pills will NOT understand packs.
   Recommended two-stage plan: (1) pre-train on 100,000+ NIH pill images (+ simulated tampering) so the backbone learns medicine appearance/print/colour artefacts;
   (2) fine-tune with `--init-from` on packaging photos (your own + rows 2-3). Stage 2 is what decides how the app behaves on packs.
6. ePillID is NOT used for training (overlaps NIH).

## F. Technical notes (for viva)
- **Duplicate removal:** perceptual dHash, exact-hash duplicates dropped (near-duplicates may remain).
- **Image quality filter:** minimum size + Laplacian-variance blur filter (same idea as the app's "unclear image" check).
- **Class imbalance:** class weights during training + report per-class precision/recall.
- **Data leakage:** split by group (`--group-by-prefix`), and each simulated fake stays in the same split as its source image.
- **Split:** 70 / 15 / 15 train / validation / test, fixed seed 42.
- **Augmentation:** small rotation, zoom, contrast, brightness (no horizontal flip - mirrored text is unrealistic), applied only during training.

## G. Leakage warning for the NIH images
The NIH file names are random IDs, they do NOT contain the product code. So the same pill product photographed several times can end up in both
train and test, which makes the test accuracy look better than it is. The downloader adds the disc number to each name (`D017_...`) and
`--group-by-prefix` then keeps whole discs together. This is a **heuristic** (I have not verified that one product stays inside one disc).
Treat NIH-only test accuracy as optimistic. The honest test is the PACK photos you collect yourself (group them by pack name).
