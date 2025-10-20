#!/usr/bin/env python3
"""
OCR модуль с НОВОЙ архитектурой (batch_first=True, resnet_proj)
Используется checkpoint best.pt из train_baseline.py
"""

import json
import math
import os
import numpy as np
import torch
import torch.nn as nn
from torchvision.models import resnet50, ResNet50_Weights
import torchvision.transforms as transforms
from PIL import Image


class ModelParameters:
    def __init__(self):
        self.batch_size = 16
        self.hidden = 512
        self.enc_layers = 1
        self.dec_layers = 1
        self.nhead = 4
        self.dropout = 0.1
        self.width = 1024
        self.height = 128


def labels_to_text(s, idx2p):
    S = "".join([idx2p[i] for i in s])
    return S if 'EOS' not in S else S[:S.find('EOS')]


class PositionalEncoding(nn.Module):
    def __init__(self, d_model, dropout=0.1, max_len=5000):
        super().__init__()
        self.dropout = nn.Dropout(p=dropout)
        self.scale = nn.Parameter(torch.ones(1))
        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)
        pe = pe.unsqueeze(0)  # Shape: (1, max_len, d_model)
        self.register_buffer('pe', pe)

    def forward(self, x):
        # x shape: (batch_size, seq_len, d_model)
        x = x + self.scale * self.pe[:, :x.size(1), :]
        return self.dropout(x)


class TransformerModel(nn.Module):
    def __init__(self, vocab_size, hidden=128, enc_layers=1, dec_layers=1, nhead=1, dropout=0.1, pretrained=True):
        super().__init__()
        if pretrained:
            backbone = resnet50(weights=ResNet50_Weights.IMAGENET1K_V2)
        else:
            backbone = resnet50(weights=None)
        modules = list(backbone.children())[:-2]
        self.backbone = nn.Sequential(*modules)
        self.resnet_proj = nn.Conv2d(2048, hidden, 1)

        self.pos_encoder = PositionalEncoding(hidden, dropout)
        self.decoder = nn.Embedding(vocab_size, hidden)
        self.pos_decoder = PositionalEncoding(hidden, dropout)
        self.transformer = nn.Transformer(
            d_model=hidden, nhead=nhead, num_encoder_layers=enc_layers,
            num_decoder_layers=dec_layers, dim_feedforward=hidden * 4,
            dropout=dropout, activation='relu', batch_first=True
        )
        self.fc_out = nn.Linear(hidden, vocab_size)

    def generate_square_subsequent_mask(self, sz, device):
        mask = torch.triu(torch.ones(sz, sz, device=device), 1).bool()
        return mask.masked_fill(mask, float('-inf'))

    def make_len_mask(self, inp):
        return (inp == 0)

    def forward(self, src, trg):
        # Encoder
        x = self.backbone(src)
        x = self.resnet_proj(x)
        x = x.flatten(2).permute(0, 2, 1)
        src_pos = self.pos_encoder(x)

        # Decoder input
        trg_emb = self.decoder(trg)
        trg_pos = self.pos_decoder(trg_emb)

        # Masking
        trg_mask = self.generate_square_subsequent_mask(trg.size(1), trg.device)
        src_key_padding_mask = None
        trg_key_padding_mask = self.make_len_mask(trg)

        # Transformer forward
        output = self.transformer(
            src=src_pos,
            tgt=trg_pos,
            tgt_mask=trg_mask,
            src_key_padding_mask=src_key_padding_mask,
            tgt_key_padding_mask=trg_key_padding_mask,
        )
        output = self.fc_out(output)
        return output

    def forward_encoder(self, src):
        """Encodes the source image batch into memory for decoding (batch_first=True)."""
        x = self.backbone(src)  # shape: (batch, 2048, h, w)
        x = self.resnet_proj(x)  # shape: (batch, hidden, h, w)
        x = x.flatten(2).permute(0, 2, 1)  # shape: (batch, seq_len, hidden)
        src_pos = self.pos_encoder(x)
        memory = self.transformer.encoder(src_pos)
        return memory  # shape: (batch, seq_len, hidden)

    def forward_decoder(self, trg, memory):
        """Decodes output tokens using encoder memory. Assumes trg shape: (batch, tgt_seq_len)."""
        trg_emb = self.decoder(trg)
        trg_pos = self.pos_decoder(trg_emb)
        trg_mask = self.generate_square_subsequent_mask(trg.size(1), trg.device)
        trg_key_padding_mask = self.make_len_mask(trg)
        output = self.transformer.decoder(
            tgt=trg_pos,
            memory=memory,
            tgt_mask=trg_mask,
            tgt_key_padding_mask=trg_key_padding_mask,
        )
        output = self.fc_out(output)
        return output


class OCRPredictor:
    def __init__(self, checkpoint_path=None):
        if checkpoint_path is None:
            # Определяем путь относительно этого файла
            current_dir = os.path.dirname(os.path.abspath(__file__))
            checkpoint_path = os.path.join(current_dir, "models", "best.pt")
        self.device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        self.params = ModelParameters()
        
        # Загружаем checkpoint
        checkpoint = torch.load(checkpoint_path, map_location=self.device)
        
        # Извлекаем алфавит из checkpoint'а
        if 'vocab' in checkpoint:
            self.p2idx = checkpoint['vocab']
            self.idx2p = {idx: char for char, idx in self.p2idx.items()}
            self.letters = list(self.p2idx.keys())
        else:
            # Fallback к стандартному алфавиту (106 символов)
            letters_ = list(
                ' !"%\'()*+,-./0123456789:;<=>?\\АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмнопрстуфхцчшщъыьэюя№'
                'ѣѳѵіїѐѓєѕіїјљњћќѝўџѡѣѥѧѩѫѭѯѱѳѵѷѹѻѽѿҁ҂ҋҌҍҎҏҐґҒғҔҕҖҗҘҙҚқҜҝҞҟҠҡҢңҤҥҦҧҨҩҪҫҬҭҮүҰұҲҳҴҵҶҷҸҹҺһҼҽҾҿӀӁӂӃӄӅӆӇӈӉӊӋӌӍӎӏӐӑӒӓӔӕӖӗӘәӚӛӜӝӞӟӠӡӢӣӤӥӦӧӨөӪӫӬӭӮӯӰӱӲӳӴӵӶӷӸӹӺӻӼӽӾӿԀԁԂԃԄԅԆԇԈԉԊԋԌԍԎԏԐԑԒԓԔԕԖԗԘԙԚԛԜԝԞԟԠԡԢԣԤԥԦԧԨԩԪԫԬԭԮԯꙀꙁꙂꙃꙄꙅꙆꙇꙈꙉꙊꙋꙌꙍꙎꙏꙐꙑꙒꙓꙔꙕꙖꙗꙘꙙꙚꙛꙜꙝꙞꙟꙠꙡꙢꙣꙤꙥꙦꙧꙨꙩꙪꙫꙬ'
            )
            self.letters = ['PAD', 'SOS'] + list(letters_) + ['EOS']
            self.p2idx = {char: i for i, char in enumerate(self.letters)}
            self.idx2p = {i: char for i, char in enumerate(self.letters)}

        # Создаем модель
        self.model = TransformerModel(
            vocab_size=len(self.letters), 
            hidden=self.params.hidden,
            enc_layers=self.params.enc_layers,
            dec_layers=self.params.dec_layers, 
            nhead=self.params.nhead,
            dropout=self.params.dropout,
            pretrained=True
        ).to(self.device)

        # Загружаем веса
        if 'model' in checkpoint:
            self.model.load_state_dict(checkpoint['model'])
        else:
            self.model.load_state_dict(checkpoint)
        
        # Создаем трансформации ТОЧНО как в TextLoader
        self.transform_eval = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((self.params.height, self.params.width)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

    def preprocess_image(self, img):
        """ТОЧНАЯ предобработка как в TextLoader (dataset.py)."""
        # Конвертируем grayscale в 3-канальное
        if img.ndim == 2:
            img = np.stack([img] * 3, axis=-1)
        
        # Применяем трансформации
        img_tensor = self.transform_eval(img)
        return img_tensor

    def predict(self, images):
        """
        Предсказывает текст для списка изображений.
        ТОЧНО повторяет логику validate() из train_baseline.py.
        
        Args:
            images: Список grayscale изображений (numpy arrays)
        
        Returns:
            (predictions, confidences)
        """
        self.model.eval()
        predictions = []
        confidences = []
        
        with torch.no_grad():
            for img in images:
                # Предобработка изображения
                img_tensor = self.preprocess_image(img)
                src = img_tensor.unsqueeze(0).to(self.device)  # (1, 3, H, W)
                
                # ТОЧНАЯ логика inference из validate()
                batch_size = src.shape[0]  # = 1
                start_token = self.p2idx['SOS']
                end_token = self.p2idx['EOS']

                # Encode image features
                memory = self.model.forward_encoder(src)  # shape: (batch, src_seq_len, hidden)

                # Prepare decoder input: start with SOS token
                trg_tensor = torch.full((batch_size, 1), start_token, dtype=torch.long, device=self.device)
                out_indexes = [[start_token] for _ in range(batch_size)]

                for _ in range(100):  # Maximum sequence length
                    output = self.model.forward_decoder(trg_tensor, memory)  # (batch, cur_seq_len, vocab_size)
                    output_last_token = output[:, -1, :]  # (batch, vocab_size)
                    out_tokens = output_last_token.argmax(dim=1)  # (batch,)
                    
                    for b_idx in range(batch_size):
                        if out_indexes[b_idx][-1] != end_token:
                            out_indexes[b_idx].append(out_tokens[b_idx].item())
                    
                    # Prepare next decoder input
                    out_tokens_unsqueezed = out_tokens.unsqueeze(1)  # (batch, 1)
                    trg_tensor = torch.cat([trg_tensor, out_tokens_unsqueezed], dim=1)
                    
                    # Stop early if all sequences finished
                    if all(idx_list[-1] == end_token for idx_list in out_indexes):
                        break

                # Post-processing
                for b_idx in range(batch_size):
                    # Generated output (skip SOS, remove EOS)
                    out_p_indices = out_indexes[b_idx][1:]
                    out_p_indices = [idx for idx in out_p_indices if idx != end_token]
                    out_p = labels_to_text(out_p_indices, self.idx2p)
                    
                    predictions.append(out_p)
                    confidences.append(1.0)  # Placeholder
        
        return predictions, confidences


if __name__ == '__main__':
    import cv2
    
    print("🔬 ТЕСТ НОВОЙ АРХИТЕКТУРЫ В ocr.py")
    print("=" * 60)
    
    # Тестовые изображения
    image_filenames = [
        "/home/fastmri/data/hackathon/train_yandex_archive/train/images/data_1d9e507a-619c-4d8f-8ff4-b87d3ecddb70_100_09b25871-6422-470e-8b89-198b653187f0.jpg"
    ] * 3
    
    images = []
    for filename in image_filenames:
        img = cv2.imread(filename, cv2.IMREAD_GRAYSCALE)
        if img is not None:
            images.append(img)
    
    if not images:
        print("❌ Не удалось загрузить изображения")
    else:
        print(f"Загружено {len(images)} изображений")
        print(f"Размер первого изображения: {images[0].shape}")
        
        predictor = OCRPredictor()
        texts, confidences = predictor.predict(images)
        
        print(f"\n📝 РЕЗУЛЬТАТЫ:")
        for i, (text, conf) in enumerate(zip(texts, confidences)):
            print(f"  [{i}] '{text}' (confidence: {conf:.4f})")
        print("=" * 60)
        print("✅ Тест завершен!")
