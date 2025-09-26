import cv2
import math
import numpy as np
import torch
import torch.nn as nn
from torchvision import models

from ocr_parameters import labels_to_text, process_image, ModelParameters


class ImageLoader(torch.utils.data.Dataset):
    def __init__(self, images):
        self.images = images

    def __getitem__(self, index):
        return self.images[index]

    def __len__(self):
        return len(self.images)


class PositionalEncoding(nn.Module):
    def __init__(self, d_model, dropout=0.1, max_len=5000):
        super(PositionalEncoding, self).__init__()
        self.dropout = nn.Dropout(p=dropout)
        self.scale = nn.Parameter(torch.ones(1))

        pe = torch.zeros(max_len, d_model)
        position = torch.arange(0, max_len, dtype=torch.float).unsqueeze(1)
        div_term = torch.exp(torch.arange(
            0, d_model, 2).float() * (-math.log(10000.0) / d_model))
        pe[:, 0::2] = torch.sin(position * div_term)
        pe[:, 1::2] = torch.cos(position * div_term)

        pe = pe.unsqueeze(0).transpose(0, 1)
        self.register_buffer('pe', pe)

    def forward(self, x):
        x = x + self.scale * self.pe[:x.size(0), :]
        return self.dropout(x)


class TransformerModel(nn.Module):
    def __init__(self, name, outtoken, hidden=128, enc_layers=1, dec_layers=1, nhead=1, dropout=0.1, pretrained=False):
        super(TransformerModel, self).__init__()
        self.backbone = models.__getattribute__(name)(pretrained=pretrained)
        # self.backbone.avgpool = nn.MaxPool2d((4, 1))
        self.backbone.fc = nn.Conv2d(2048, hidden // 4, 1)

        self.pos_encoder = PositionalEncoding(hidden, dropout)
        self.decoder = nn.Embedding(outtoken, hidden)
        self.pos_decoder = PositionalEncoding(hidden, dropout)
        self.transformer = nn.Transformer(d_model=hidden, nhead=nhead, num_encoder_layers=enc_layers,
                                          num_decoder_layers=dec_layers, dim_feedforward=hidden * 4, dropout=dropout,
                                          activation='relu')

        self.fc_out = nn.Linear(hidden, outtoken)
        self.src_mask = None
        self.trg_mask = None
        self.memory_mask = None

    def generate_square_subsequent_mask(self, sz):
        mask = torch.triu(torch.ones(sz, sz), 1)
        mask = mask.masked_fill(mask == 1, float('-inf'))
        return mask

    def make_len_mask(self, inp):
        return (inp == 0).transpose(0, 1)

    def forward(self, src, trg):
        if self.trg_mask is None or self.trg_mask.size(0) != len(trg):
            self.trg_mask = self.generate_square_subsequent_mask(len(trg)).to(trg.device)

        x = self.backbone.conv1(src)
        x = self.backbone.bn1(x)
        x = self.backbone.relu(x)
        x = self.backbone.maxpool(x)
        x = self.backbone.layer1(x)
        x = self.backbone.layer2(x)
        x = self.backbone.layer3(x)
        x = self.backbone.layer4(x)

        x = self.backbone.fc(x)
        x = x.permute(0, 3, 1, 2).flatten(2).permute(1, 0, 2)
        src_pad_mask = self.make_len_mask(x[:, :, 0])
        src = self.pos_encoder(x)

        trg_pad_mask = self.make_len_mask(trg)
        trg = self.decoder(trg)
        trg = self.pos_decoder(trg)

        output = self.transformer(src, trg, src_mask=self.src_mask, tgt_mask=self.trg_mask,
                                  memory_mask=self.memory_mask,
                                  src_key_padding_mask=src_pad_mask, tgt_key_padding_mask=trg_pad_mask,
                                  memory_key_padding_mask=src_pad_mask)
        output = self.fc_out(output)

        return output


class OCRPredictor:
    def __init__(self, checkpoint_path="./models/transformer_v2.0.pt"):
        self.device = torch.device('cpu')
        self.params = ModelParameters()

        letters_ = list(
            ' !"%\'()*+,-./0123456789:;<=>?\\АБВГДЕЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯабвгдежзийклмнопрстуфхцчшщъыьэюя№')
        self.letters = ['PAD', 'SOS'] + letters_ + ['EOS']

        self.char_to_index = {char: i for i, char in enumerate(self.letters)}
        self.index_to_char = {i: char for i, char in enumerate(self.letters)}

        self.model = TransformerModel('resnet50', len(self.letters), hidden=self.params.hidden,
                                      enc_layers=self.params.enc_layers,
                                      dec_layers=self.params.dec_layers, nhead=self.params.nhead,
                                      dropout=self.params.dropout).to(self.device)

        checkpoint = torch.load(checkpoint_path, map_location=torch.device('cpu'))
        self.model.load_state_dict(checkpoint)

    def predict(self, images):
        self.model.eval()

        text_labels = []
        confidence = []

        with torch.no_grad():
            for img in images:
                img = process_image(img, self.params).astype('uint8')
                img = img / img.max()
                img = np.transpose(img, (2, 0, 1))

                src = torch.FloatTensor(img).unsqueeze(0).cpu()

                x = self.model.backbone.conv1(src)
                x = self.model.backbone.bn1(x)
                x = self.model.backbone.relu(x)
                x = self.model.backbone.maxpool(x)

                x = self.model.backbone.layer1(x)
                x = self.model.backbone.layer2(x)
                x = self.model.backbone.layer3(x)
                x = self.model.backbone.layer4(x)
                x = self.model.backbone.fc(x)
                x = x.permute(0, 3, 1, 2).flatten(2).permute(1, 0, 2)
                memory = self.model.transformer.encoder(self.model.pos_encoder(x))

                string_confidence = 1
                out_indexes = [self.char_to_index['SOS'], ]
                for i in range(200):
                    trg_tensor = torch.LongTensor(out_indexes).unsqueeze(1).to(self.device)
                    output = self.model.fc_out(
                        self.model.transformer.decoder(self.model.pos_decoder(self.model.decoder(trg_tensor)), memory))

                    out_token = output.argmax(2)[-1].item()
                    string_confidence = string_confidence * torch.sigmoid(output[-1, 0, out_token]).item()
                    out_indexes.append(out_token)
                    if out_token == self.char_to_index['EOS']:
                        break

                label = labels_to_text(out_indexes[1:], self.index_to_char)
                text_labels.append(label)
                confidence.append(string_confidence)

        return text_labels, confidence


if __name__ == '__main__':
    import time

    t1 = time.time()
    image_filenames = [ "/home/linuxovich/ocr-analysis/000001482.JPG"]* 5 

    images = [cv2.imread(filename, cv2.IMREAD_GRAYSCALE) for filename in image_filenames]
    print(images[0].shape)

    predictor = OCRPredictor()
    texts, confidences = predictor.predict(images)
    print(texts)
    print(confidences)
    print("TIME", time.time() - t1)