import os
import argparse
from pathlib import Path
from PIL import Image
from datetime import datetime
import random
import numpy as np
import torch
from torch.utils.data import Dataset, random_split
from torchvision import transforms
from transformers import TrOCRProcessor, VisionEncoderDecoderModel, Seq2SeqTrainer, Seq2SeqTrainingArguments
import evaluate

def build_vocab(words_dir):
    chars = set()
    for fname in os.listdir(words_dir):
        if fname.endswith('.txt'):
            with open(os.path.join(words_dir, fname), 'r', encoding='utf-8') as f:
                chars.update(f.read())
    # Remove unwanted whitespace except space
    chars = {c for c in chars if c.strip() or c == ' '}
    vocab = sorted(chars)
    return vocab

class OCRFolderDataset(Dataset):
    def __init__(self, images_dir, words_dir, processor, file_list, image_transform=None):
        self.images_dir = images_dir
        self.words_dir = words_dir
        self.processor = processor
        self.image_files = file_list
        self.image_transform = image_transform

    def __len__(self):
        return len(self.image_files)

    def __getitem__(self, idx):
        img_name = self.image_files[idx]
        img_path = os.path.join(self.images_dir, img_name)
        txt_name = os.path.splitext(img_name)[0] + '.txt'
        txt_path = os.path.join(self.words_dir, txt_name)

        # Robust loading
        try:
            image = Image.open(img_path).convert("RGB")
        except Exception as e:
            raise RuntimeError(f"Error loading image {img_path}: {e}")

        if self.image_transform:
            image = self.image_transform(image)

        try:
            with open(txt_path, 'r', encoding='utf-8') as f:
                text = f.read().strip()
        except Exception as e:
            raise RuntimeError(f"Error loading text {txt_path}: {e}")

        encoding = self.processor(image, text, return_tensors="pt", padding="max_length", truncation=True)
        encoding = {k: v.squeeze() for k, v in encoding.items()}
        return encoding

def data_collator(batch):
    pixel_values = torch.stack([item["pixel_values"] for item in batch])
    labels = torch.stack([item["labels"] for item in batch])
    return {"pixel_values": pixel_values, "labels": labels}

def parse_args():
    parser = argparse.ArgumentParser(description="Fine-tune TrOCR on a custom dataset (with augmentation)")
    parser.add_argument("--checkpoint_dir", type=Path, required=True, help="Checkpoint to continue from")
    parser.add_argument("--data_dir", type=str, required=True, help="Path to the root data directory")
    parser.add_argument("--batch_size", type=int, default=8, help="Batch size for training and evaluation")
    parser.add_argument("--num_epochs", type=int, default=5, help="Number of training epochs")
    parser.add_argument("--val_split", type=float, default=0.1, help="Validation split ratio")
    parser.add_argument("--image_ext", type=str, default="jpg", help="Image file extension (e.g., jpg, png)")
    parser.add_argument("--run_name", type=str, default=None, help="Run name for tensorboard logging")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")

    
    return parser.parse_args()

def train_trocr_model(args):
    args.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    images_dir = os.path.join(args.data_dir, "images")
    words_dir = os.path.join(args.data_dir, "texts")
    run_name = args.run_name or f"trocr-finetune-{datetime.now().strftime('%Y%m%d-%H%M%S')}"

    # Reproducibility
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(args.seed)

    # 1. Load processor and model, add new tokens, resize model
    if args.checkpoint_dir.is_dir() and not any(args.checkpoint_dir.iterdir()):
        try:
            processor = TrOCRProcessor.from_pretrained(args.checkpoint_dir)
            model = VisionEncoderDecoderModel.from_pretrained(args.checkpoint_dir)
        except Exception as ex:
            print(f"Failed to load checkpoint from {args.checkpoint_dir}")
            processor = TrOCRProcessor.from_pretrained('kazars24/trocr-base-handwritten-ru')
            model = VisionEncoderDecoderModel.from_pretrained('kazars24/trocr-base-handwritten-ru')
    else:
        processor = TrOCRProcessor.from_pretrained('kazars24/trocr-base-handwritten-ru')
        model = VisionEncoderDecoderModel.from_pretrained('kazars24/trocr-base-handwritten-ru')
            

    # 2. Build vocabulary and update tokenizer
    new_tokens = build_vocab(words_dir)
    num_added = processor.tokenizer.add_tokens(new_tokens)
    print(f"Added {num_added} new tokens.")
    model.decoder.resize_token_embeddings(len(processor.tokenizer))
    print(f"Vocab size: {len(processor.tokenizer)}")

    # 3. Prepare file list (ensure paired files)
    allowed_exts = {args.image_ext.lower(), "png", "jpg"}
    file_list = [
        f for f in os.listdir(images_dir)
        if f.split(".")[-1].lower() in allowed_exts
        and os.path.exists(os.path.join(words_dir, os.path.splitext(f)[0] + ".txt"))
    ]
    if len(file_list) == 0:
        raise RuntimeError("No paired image/text files found.")

    image_transform = transforms.Compose([
        transforms.Resize((int(128 * 1.05), int(1024 * 1.05))),
        transforms.RandomCrop((128, 1024)),
        transforms.RandomRotation(degrees=2, fill=(255, 255, 255)),
    ])

    dataset = OCRFolderDataset(images_dir, words_dir, processor, file_list, image_transform=image_transform)

    # 5. Split into train/val
    val_size = int(args.val_split * len(dataset))
    train_size = len(dataset) - val_size
    train_dataset, val_dataset = random_split(dataset, [train_size, val_size])

    # 6. Load metrics
    wer_metric = evaluate.load("wer")
    cer_metric = evaluate.load("cer")

    def compute_metrics(pred):
        pred_ids = pred.predictions
        label_ids = pred.label_ids
        pred_str = [s.strip() for s in processor.batch_decode(pred_ids, skip_special_tokens=True)]
        label_ids[label_ids == -100] = processor.tokenizer.pad_token_id
        label_str = [s.strip() for s in processor.batch_decode(label_ids, skip_special_tokens=True)]
        wer = wer_metric.compute(predictions=pred_str, references=label_str)
        cer = cer_metric.compute(predictions=pred_str, references=label_str)
        return {"wer": wer, "cer": cer}

    # 7. Training arguments
    training_args = Seq2SeqTrainingArguments(
        output_dir=args.checkpoint_dir,
        per_device_train_batch_size=args.batch_size,
        per_device_eval_batch_size=args.batch_size,
        num_train_epochs=args.num_epochs,
        logging_steps=10,
        save_steps=50,
        save_total_limit=2,
        predict_with_generate=True,
        fp16=torch.cuda.is_available(),
        report_to="tensorboard",
        logging_dir=os.path.join(args.checkpoint_dir, "runs", run_name),
        eval_steps=10, 
    )

    # 8. Trainer
    trainer = Seq2SeqTrainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        data_collator=data_collator,
        tokenizer=processor.tokenizer,
        compute_metrics=compute_metrics,
    )

    # 9. Train!
    trainer.train()

    # 10. Save the updated model and processor
    trainer.save_model(args.checkpoint_dir)
    processor.save_pretrained(args.checkpoint_dir)

if __name__ == "__main__":
    args = parse_args()
    train_trocr_model(args)