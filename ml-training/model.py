import torch
import torch.nn as nn
import math
from torchvision import models

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
        pe = pe.unsqueeze(0).transpose(0, 1)
        self.register_buffer('pe', pe)

    def forward(self, x):
        x = x + self.scale * self.pe[:x.size(0), :]
        return self.dropout(x)

class TransformerModel(nn.Module):
    def __init__(self, name, outtoken, hidden=128, enc_layers=1, dec_layers=1, nhead=1, dropout=0.1, pretrained=False):
        super().__init__()
        self.backbone = models.__getattribute__(name)(pretrained=pretrained)
        self.backbone.fc = nn.Conv2d(2048, hidden, 1)
        self.pos_encoder = PositionalEncoding(hidden, dropout)
        self.decoder = nn.Embedding(outtoken, hidden)
        self.pos_decoder = PositionalEncoding(hidden, dropout)
        self.transformer = nn.Transformer(
            d_model=hidden, nhead=nhead, num_encoder_layers=enc_layers,
            num_decoder_layers=dec_layers, dim_feedforward=hidden*4,
            dropout=dropout, activation='relu'
        )
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
        
        b, c, h, w = x.shape
        x = x.permute(0, 2, 3, 1).reshape(b, h*w, c)  # (batch, seq_len, 512)
        x = x.permute(1, 0, 2)  # (seq_len, batch, 512)
        src_pad_mask = self.make_len_mask(x[:,:,0])
        src = self.pos_encoder(x)
        trg_pad_mask = self.make_len_mask(trg)
        trg = self.decoder(trg)
        trg = self.pos_decoder(trg)
        output = self.transformer(
            src, trg, src_mask=self.src_mask, tgt_mask=self.trg_mask, memory_mask=self.memory_mask,
            src_key_padding_mask=src_pad_mask, tgt_key_padding_mask=trg_pad_mask, memory_key_padding_mask=src_pad_mask
        )
        return self.fc_out(output)
    
# class TransformerModel(nn.Module):
#     def __init__(self, name, outtoken, hidden=128, enc_layers=1, dec_layers=1, nhead=1, dropout=0.1, pretrained=False):
#         super().__init__()
#         self.backbone = models.__getattribute__(name)(pretrained=pretrained)
#         self.backbone.fc = nn.Conv2d(2048, hidden // 4, 1)
#         self.pos_encoder = PositionalEncoding(hidden, dropout)
#         self.decoder = nn.Embedding(outtoken, hidden)
#         self.pos_decoder = PositionalEncoding(hidden, dropout)
#         self.transformer = nn.Transformer(d_model=hidden, nhead=nhead, num_encoder_layers=enc_layers,
#                                           num_decoder_layers=dec_layers, dim_feedforward=hidden * 4, dropout=dropout,
#                                           activation='relu')
#         self.fc_out = nn.Linear(hidden, outtoken)
#         self.src_mask = None
#         self.trg_mask = None
#         self.memory_mask = None

#     def generate_square_subsequent_mask(self, sz):
#         mask = torch.triu(torch.ones(sz, sz), 1)
#         mask = mask.masked_fill(mask == 1, float('-inf'))
#         return mask

#     def make_len_mask(self, inp):
#         return (inp == 0).transpose(0, 1)

#     def forward(self, src, trg):
#         if self.trg_mask is None or self.trg_mask.size(0) != len(trg):
#             self.trg_mask = self.generate_square_subsequent_mask(len(trg)).to(trg.device)
#         x = self.backbone.conv1(src)
#         x = self.backbone.bn1(x)
#         x = self.backbone.relu(x)
#         x = self.backbone.maxpool(x)
#         x = self.backbone.layer1(x)
#         x = self.backbone.layer2(x)
#         x = self.backbone.layer3(x)
#         x = self.backbone.layer4(x)
#         x = self.backbone.fc(x)
#         x = x.permute(0, 3, 1, 2).flatten(2).permute(1, 0, 2)
#         src_pad_mask = self.make_len_mask(x[:, :, 0])
#         src = self.pos_encoder(x)
#         trg_pad_mask = self.make_len_mask(trg)
#         trg = self.decoder(trg)
#         trg = self.pos_decoder(trg)
#         output = self.transformer(
#             src, trg,
#             src_mask=self.src_mask, tgt_mask=self.trg_mask,
#             memory_mask=self.memory_mask,
#             src_key_padding_mask=src_pad_mask, tgt_key_padding_mask=trg_pad_mask,
#             memory_key_padding_mask=src_pad_mask,
#         )
#         output = self.fc_out(output)
#         return output