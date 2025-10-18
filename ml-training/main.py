from pathlib import Path
from prepare_data import prepare_dataset
import torch
import random
import os
from hparams import Hparams
from utils import process_texts, labels_to_text, generate_data, count_parameters
from dataset import TextLoader, TextCollate
from model import TransformerModel
from train_baseline import train_baseline_model
import torch.optim as optim
import argparse
from train_trocr import train_trocr_model
from aiohttp import web
from threading import Thread


def set_seed(seed=6666):
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)

def train_baseline(hp):
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
    train_size = int(0.8 * len(names))
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
    model = TransformerModel('resnet50', len(letters), hidden=hp.hidden, enc_layers=hp.enc_layers,
                            dec_layers=hp.dec_layers, nhead=hp.nhead, dropout=hp.dropout, pretrained=True).to(device)
    optimizer = optim.AdamW(model.parameters(), lr=hp.lr)
    criterion = torch.nn.CrossEntropyLoss(ignore_index=p2idx['PAD'])
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, 'min')

    valid_loss_all, train_loss_all, eval_accuracy_all, eval_loss_cer_all = [], [], [], []
    epochs, best_eval_loss_cer = 0, float('inf')

    print(f'The model has {count_parameters(model):,} trainable parameters')
    train_baseline_model(model, optimizer, criterion, train_loader, val_loader, scheduler, best_eval_loss_cer,
              device, epochs, valid_loss_all, train_loss_all, eval_loss_cer_all, eval_accuracy_all,
              labels_to_text, idx2p=idx2p, p2idx=p2idx, max_epochs=100, checkpoint_dir=hp.checkpoint_dir)


def start_model_training(model, labels_dir, checkpoint_dir, input_image_dir):
    parser = argparse.ArgumentParser(description='TransformerModel training')
    parser.add_argument('--destination_dir', type=Path, default='./data/train', help='Destination directory for output images and texts')
    
    args = parser.parse_args()
    
    args.destination_dir.mkdir(parents=True, exist_ok=True)
    args.model = model
    args.checkpoint_dir = checkpoint_dir
    args.labels_dir = labels_dir
    args.input_image_dir = input_image_dir
    
    
    summary = prepare_dataset(args)
    
    if summary.get("total", 0) < 10:
        exit(0)

    if args.model == 'baseline':
        hp = Hparams()
        hp.checkpoint_dir = args.checkpoint_dir
        hp.trans_dir = summary.get("text_dir")
        hp.image_dir = summary.get("image_dir")
        train_baseline(hp=hp)
    else:
        args.data_dir = Path(summary.get("image_dir")).parent
        train_trocr_model(args)

def main(request):
    try:
        model = request.query.get('model')
        checkpoint_dir = request.query.get('checkpoint_dir')
        labels_dir = request.query.get('labels_dir')
        input_image_dir = request.query.get('input_image_dir')

        Thread(target=start_model_training, args=(model, labels_dir, checkpoint_dir, input_image_dir), daemon=True).start()
        return web.json_response({"status": "accepted"}, status=202)
    except Exception as e:
        print(f"Fatal error: {str(e)}")
        return web.json_response({"error": str(e)}, status=500)

def health_check(request):
    return web.json_response({"status": "ok"}, status=200)

if __name__ == "__main__":
    app = web.Application()
    app.add_routes([web.get('/', health_check)])
    app.add_routes([web.get('/train', main)])
    web.run_app(app, port=int(os.getenv("PORT", "8080")))

    
    