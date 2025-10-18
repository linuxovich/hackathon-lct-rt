# OCR Transformer for Handwritten Text Recognition

This project implements an OCR (Optical Character Recognition) pipeline based on a Transformer model with a ResNet backbone for recognizing handwritten or printed text in images. The code is refactored for clarity, modularity, and ease of experimentation.

---

## Project Structure

```
ml-training/
│
├── main.py              # Main training & validation entry point
├── hparams.py           # Hyperparameters and configuration
├── utils.py             # Utility functions (text, image, metrics, etc.)
├── dataset.py           # Dataset and batch collation logic
├── model.py             # Model definition (ResNet+Transformer)
├── train_baseline.py    # Training and validation routines for baseline model 
├── train_tr_ocr.py      # Training and validation routines for TrOcr model
├── prepare_data.py      # Prepares training data
├── log/                 # Logs, checkpoints, predictions (created automatically)
└── README.md            # This documentation
```

---

## Data Setup

- **Labels:** Directory of JSON files or plain text files containing ground truth label strings.
- **Images:** Directory of input images (`.jpg`/`.png`).

Files must correspond by name. Example:

```
images/
    img1.jpg
    img2.jpg
words/
    img1.txt    # or img1.json, with text label inside
    img2.txt
```

---

### 2. Prepare your data

Organize images and corresponding labels as specified above.

### 3. Run Training

### Build the Docker image

Inside your `ml-training/` project directory, run:

```bash
docker build -t hackaton-ml-training .
```

#### **Example (Baseline Model):**
```bash
docker run --gpus all --rm -it \
  -v /absolute/path/to/your/images:/workspace/images \
  -v /absolute/path/to/your/labels:/workspace/labels \
  -v /absolute/path/to/your/checkpoints:/workspace/log/baseline_checkpoints \
  hackaton-ml-training \
  --model baseline \
  --checkpoint_dir /workspace/log/baseline_checkpoints \
  --labels_dir /workspace/labels \
  --input_image_dir /workspace/images \
  --destination_dir /workspace/data/train
```

#### **Example (TrOCR Model):**
```bash
docker run --gpus all --rm -it \
  -v /absolute/path/to/your/images:/workspace/images \
  -v /absolute/path/to/your/labels:/workspace/labels \
  -v /absolute/path/to/your/checkpoints:/workspace/log/trocr_checkpoints \
  hackaton-ml-training \
  --model trocr \
  --checkpoint_dir /workspace/log/trocr_checkpoints \
  --labels_dir /workspace/labels \
  --input_image_dir /workspace/images \
  --destination_dir /workspace/data/train
```

- `--gpus all` enables GPU usage if available.
- `-v` mounts host folders (for images, labels, and output checkpoints/directories) into the container.
- Adjust source (`/absolute/path/to/...`) and target (`/workspace/...`) directories as needed for your setup.

#### Train Baseline Model

```bash
python main.py \
  --model baseline \
  --checkpoint_dir ./log/baseline_checkpoints \
  --labels_dir /path/to/labels \
  --input_image_dir /path/to/images \
  --destination_dir ./data/train
```

#### Train TrOCR Model

```bash
python main.py \
  --model trocr \
  --checkpoint_dir ./log/trocr_checkpoints \
  --labels_dir /path/to/labels \
  --input_image_dir /path/to/images \
  --destination_dir ./data/train
```
- `--destination_dir` is where prepared/processed data will be stored (default: `./data/train`).

---

### 4. Checkpoints & Logs

- Training logs, checkpoints, and intermediate outputs are stored in the directory given by `--checkpoint_dir`.
- Logs are also in `./log/` by default.

---

### 5. Hyperparameters

Default hyperparameters for the baseline model are set in `hparams.py`. To tweak LR, batch size, etc., edit that file or extend with argument parsing as needed.

---

## CLI Arguments Summary

- `--model`          Model type to train: `baseline` or `trocr`. Default: `trocr`.
- `--checkpoint_dir` Directory in which to store checkpoints (required).
- `--labels_dir`     Directory containing label files (`.txt` or JSON) (required).
- `--input_image_dir` Directory of source images (required).
- `--destination_dir` Output location for prepared data (default: `./data/train`).

---

## Code Overview

- **`main.py`**: Sets seeds, loads data, initializes model, starts training/validation loops.
- **`hparams.py`**: Stores all configuration for dataset locations and model/training hyperparameters.
- **`utils.py`**: Preprocessing functions for images and labels; also computes metrics like phoneme error rate.
- **`dataset.py`**: PyTorch `Dataset` and batch collate logic for efficient batching.
- **`model.py`**: Contains `TransformerModel` (ResNet backbone + Transformer) and positional encoding.
- **`train_trocr.py`**: train TrOCR model
- **`train_baseline.py`**: Training baseline model
- **`prepare_data.py`**: prepares the training data 
