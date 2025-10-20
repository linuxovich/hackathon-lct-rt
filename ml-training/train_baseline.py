import argparse
from datetime import datetime
import json
from pathlib import Path
from hparams import Hparams
import torch
from tqdm import tqdm
import editdistance
import matplotlib.pyplot as plt
import time
import os
import random
from utils import process_texts, labels_to_text, generate_data, count_parameters
from dataset import TextLoader, TextCollate
from model import TransformerModel
import torch.optim as optim

def set_seed(seed=6666):
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)

def train(model, optimizer, criterion, iterator, device):
    """Training loop for a single epoch."""
    model.train()
    epoch_loss = 0
    for (src, trg) in tqdm(iterator, desc="Training"):
        src, trg = src.to(device), trg.to(device)
        optimizer.zero_grad()
        
        # output = model(src, trg[:-1, :])
        output = model(src, trg[:, :-1])
        loss = criterion(output.reshape(-1, output.shape[-1]), trg[:, 1:].reshape(-1))
        
        loss.backward()
        optimizer.step()
        epoch_loss += loss.item()
    return epoch_loss / len(iterator)

def evaluate(model, criterion, iterator, device):
    """Evaluation loop for a single epoch (calculates loss)."""
    model.eval()
    epoch_loss = 0
    with torch.no_grad():
        for (src, trg) in tqdm(iterator, desc="Evaluating"):
            src, trg = src.to(device), trg.to(device)
            output = model(src, trg[:, :-1])
            loss = criterion(output.reshape(-1, output.shape[-1]), trg[:, 1:].reshape(-1))
            epoch_loss += loss.item()
    return epoch_loss / len(iterator)

def validate(model, dataloader, device, show=10, labels_to_text=None, idx2p=None, p2idx=None):
    """
    Validation loop for computing CER and WER with auto-regressive decoding.

    Args:
        model: The trained Transformer model.
        dataloader: The validation DataLoader.
        device: The device to run the model on.
        show: The number of examples to print.
        labels_to_text: A function to convert label indices to text.
        idx2p: The index-to-character mapping.
        p2idx: The character-to-index mapping.

    Returns:
        A tuple containing (character_error_rate, word_error_rate).
    """
    model.eval()
    show_count = 0
    total_char_dist = 0
    total_chars = 0
    total_word_dist = 0
    total_words = 0

    # Ensure p2idx is available
    if not p2idx or 'SOS' not in p2idx or 'EOS' not in p2idx:
        raise ValueError("p2idx dictionary with 'SOS' and 'EOS' tokens must be provided.")

    with torch.no_grad():
        for i, (src, trg) in enumerate(dataloader):
            src, trg = src.to(device), trg.to(device)  # src: (batch, 3, H, W); trg: (batch, seq_len)
            batch_size = src.shape[0]
            start_token = p2idx['SOS']
            end_token = p2idx['EOS']

            # Encode image features
            # shape: (batch, src_seq_len, hidden)
            if isinstance(model, torch.nn.DataParallel):
                memory = model.module.forward_encoder(src)
            else:
                memory = model.forward_encoder(src)

            # Prepare decoder input: start with SOS token for each batch item
            trg_tensor = torch.full((batch_size, 1), start_token, dtype=torch.long, device=device)  # (batch, seq_len=1)
            out_indexes = [[start_token] for _ in range(batch_size)]

            for _ in range(100):  # Maximum sequence length
                if isinstance(model, torch.nn.DataParallel):
                    output = model.module.forward_decoder(trg_tensor, memory)
                else:
                    output = model.forward_decoder(trg_tensor, memory)
                  # (batch, cur_seq_len, vocab_size)
                output_last_token = output[:, -1, :]  # (batch, vocab_size)
                out_tokens = output_last_token.argmax(dim=1)  # (batch,)
                for b_idx in range(batch_size):
                    if out_indexes[b_idx][-1] != end_token:
                        out_indexes[b_idx].append(out_tokens[b_idx].item())
                # Prepare next decoder input: append token by token, seq axis=1
                out_tokens_unsqueezed = out_tokens.unsqueeze(1)  # (batch, 1)
                trg_tensor = torch.cat([trg_tensor, out_tokens_unsqueezed], dim=1)  # (batch, cur_seq_len+1)
                # Stop early if all sequences finished
                if all(idx_list[-1] == end_token for idx_list in out_indexes):
                    break

            # Post-processing and metric calculation
            for b_idx in range(batch_size):
                # Generated output (skip SOS, remove EOS)
                out_p_indices = out_indexes[b_idx][1:]
                out_p_indices = [idx for idx in out_p_indices if idx != end_token]
                out_p = labels_to_text(out_p_indices, idx2p)
                
                # Ground truth (skip SOS, remove EOS)
                real_p_indices = trg[b_idx, 1:].cpu().numpy().tolist()
                real_p_indices = [idx for idx in real_p_indices if idx != end_token]
                real_p = labels_to_text(real_p_indices, idx2p)

                # Character-level metrics
                char_dist = editdistance.eval(out_p, real_p)
                total_char_dist += char_dist
                total_chars += len(real_p)

                # Word-level metrics
                pred_words = out_p.split()
                true_words = real_p.split()
                total_word_dist += editdistance.eval(pred_words, true_words)
                total_words += len(true_words)

                if show > show_count:
                    print(f'Batch {i}, Example {b_idx}:')
                    print(f'  Real: {real_p}')
                    print(f'  Pred: {out_p}')
                    print(f'  Char ED: {char_dist}, Real Len: {len(real_p)}, CER: {char_dist / max(len(real_p), 1) * 100:.2f}%')
                    print('-' * 20)
                    show_count += 1

    # Handle division by zero
    cer = (total_char_dist / max(total_chars, 1)) * 100
    wer = (total_word_dist / max(total_words, 1)) * 100

    return cer, wer

def train_all(
    model,
    optimizer,
    criterion,
    train_loader,
    val_loader,
    scheduler,
    best_eval_loss_cer,
    device,
    epochs,
    valid_loss_all,
    train_loss_all,
    eval_loss_cer_all,
    eval_wer_all,
    labels_to_text,
    idx2p,
    p2idx,
    checkpoint_dir,
    max_epochs=15,
):
    """Main training and evaluation loop."""
    print(f"Training on device: {device}")
    count_bad = 0
    
    # Ensure checkpoint directory exists
    os.makedirs(checkpoint_dir, exist_ok=True)

    for epoch in range(epochs, max_epochs):
        print(f'Epoch: {epoch + 1:02}')
        start_time = time.time()

        # Training Loop
        print("----------- train ------------")
        train_loss = train(model, optimizer, criterion, train_loader, device)
        
        # Validation Loop (for loss)
        print("----------- valid ------------")
        valid_loss = evaluate(model, criterion, val_loader, device)
        
        # Evaluation Loop (for CER and WER)
        print("----------- eval ------------")
        eval_loss_cer, eval_wer = validate(
            model, val_loader, device, show=10, 
            labels_to_text=labels_to_text, idx2p=idx2p, p2idx=p2idx
        )
        scheduler.step(eval_loss_cer)
        
        valid_loss_all.append(valid_loss)
        train_loss_all.append(train_loss)
        eval_loss_cer_all.append(eval_loss_cer)
        eval_wer_all.append(eval_wer)

        # Robust model saving (works with or without DataParallel)
        model_state = getattr(model, 'module', model).state_dict()
        checkpoint = {
            'model': model_state,
            'epoch': epoch,
            'best_eval_loss_cer': best_eval_loss_cer,
            'valid_loss_all': valid_loss_all,
            'train_loss_all': train_loss_all,
            'eval_loss_cer_all': eval_loss_cer_all,
            'eval_wer_all': eval_wer_all,
            'vocab': p2idx,
        }

        if eval_loss_cer < best_eval_loss_cer:
            count_bad = 0
            best_eval_loss_cer = eval_loss_cer
            torch.save(checkpoint, f'{checkpoint_dir}/best.pt')
            with open(f"{checkpoint_dir}/vocab.json", 'w', encoding='utf-8') as fo:
                json.dump(p2idx, fo, ensure_ascii=False, indent=2)
            print('Save best model')
        else:
            count_bad += 1
            torch.save(checkpoint, f'{checkpoint_dir}/checkpoint_{epoch}.pt')
            print('Save model')

        print(f'Time: {time.time() - start_time:.1f}s')
        print(f'Train Loss: {train_loss:.4f}')
        print(f'Val   Loss: {valid_loss:.4f}')
        print(f'Eval  CER: {eval_loss_cer:.4f}')
        print(f'Eval  WER: {eval_wer:.4f}')

        # Plotting (only last 20 points for clarity)
        plt.clf()
        plt.plot(valid_loss_all[-20:], label="Valid Loss")
        plt.plot(train_loss_all[-20:], label="Train Loss")
        plt.legend()
        plt.savefig(f'{checkpoint_dir}/all_loss.png')
        plt.clf()
        plt.plot(eval_loss_cer_all[-20:])
        plt.savefig(f'{checkpoint_dir}/loss_cer.png')
        plt.clf()
        plt.plot(eval_wer_all[-20:])
        plt.savefig(f'{checkpoint_dir}/eval_wer.png')

        if count_bad > 5:
            print("Early stopping triggered.")
            break

def train_baseline_model(hp):
    set_seed()
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    os.makedirs("log/img", exist_ok=True)

    names, lines, cnt, all_word = process_texts(hp.image_dir, hp.trans_dir, hp)
    letters = set(cnt.keys())
    letters = sorted(list(letters))
    letters = ['PAD', 'SOS'] + letters + ['EOS']
    p2idx = {p: idx for idx, p in enumerate(letters)}
    idx2p = {idx: p for p, idx in p2idx.items()}
    
    # Data splits (modify as needed for your real criteria)
    train_size = int(0.9 * len(names))
    image_train = generate_data(names[:train_size], hp.image_dir)
    lines_train = lines[:train_size]
    image_val = generate_data(names[train_size:], hp.image_dir)
    lines_val = lines[train_size:]

    # Datasets and loaders
    train_dataset = TextLoader(image_train, lines_train, hp, p2idx=p2idx, eval=False)
    val_dataset = TextLoader(image_val, lines_val, hp, p2idx=p2idx, eval=True)
    train_loader = torch.utils.data.DataLoader(train_dataset, shuffle=True,
                                               batch_size=hp.batch_size, pin_memory=True,
                                               drop_last=True, collate_fn=TextCollate())
    val_loader = torch.utils.data.DataLoader(val_dataset, shuffle=False,
                                             batch_size=1, pin_memory=False,
                                             drop_last=False, collate_fn=TextCollate())

    # Model
    model = TransformerModel(
        len(letters), hidden=hp.hidden, enc_layers=hp.enc_layers,
        dec_layers=hp.dec_layers, nhead=hp.nhead, dropout=hp.dropout, pretrained=True
    )
    if torch.cuda.device_count() > 1:
        print("Using", torch.cuda.device_count(), "GPUs!")
        model = torch.nn.DataParallel(model)
        
    model = model.to(device)
    optimizer = optim.AdamW(model.parameters(), lr=hp.lr)
    criterion = torch.nn.CrossEntropyLoss(ignore_index=p2idx['PAD'])
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, 'min')

    valid_loss_all, train_loss_all, eval_accuracy_all, eval_loss_cer_all = [], [], [], []
    epochs, best_eval_loss_cer = 0, float('inf')

    print(f'The model has {count_parameters(model):,} trainable parameters')
    train_all(model, optimizer, criterion, train_loader, val_loader, scheduler, best_eval_loss_cer,
              device, epochs, valid_loss_all, train_loss_all, eval_loss_cer_all, eval_accuracy_all,
              labels_to_text, idx2p=idx2p, p2idx=p2idx, max_epochs=15, checkpoint_dir=hp.checkpoint_dir)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='TransformerModel training')
    parser.add_argument('--text_dir', required=True, type=Path, help='Checkpoint path to save trained model')
    parser.add_argument('--image_dir', type=str, required=True, help='Directory containing JSON label files')
    parser.add_argument('--checkpoint_dir', type=Path, default=None, help='Directory containing JSON label files')
    args = parser.parse_args()
    
    hp = Hparams()
    hp.checkpoint_dir = args.checkpoint_dir or Path(f"./logs/baseline/run-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
    hp.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    hp.trans_dir = args.text_dir
    hp.image_dir = args.image_dir
    train_baseline_model(hp=hp)
