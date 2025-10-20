from pathlib import Path
from prepare_data import prepare_dataset
import torch
import random
import os
from hparams import Hparams
from train_baseline import train_baseline_model
import argparse
from train_trocr import train_trocr_model
from aiohttp import web
from threading import Thread


def set_seed(seed=6666):
    random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)

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
        train_baseline_model(hp=hp)
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
    app.add_routes([web.get('/', main)])
    web.run_app(app, port=int(os.getenv("PORT", "8080")))

    
    
