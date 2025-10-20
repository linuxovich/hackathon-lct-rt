import torch
import torch.nn as nn
import math
from torchvision.models import resnet50, ResNet50_Weights


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
        pe = pe.unsqueeze(0) # Shape: (1, max_len, d_model)
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
        """
        Encodes the source image batch into memory for decoding (batch_first=True).
        """
        x = self.backbone(src)  # shape: (batch, 2048, h, w)
        x = self.resnet_proj(x)  # shape: (batch, hidden, h, w)
        x = x.flatten(2).permute(0, 2, 1)  # shape: (batch, seq_len, hidden)
        src_pos = self.pos_encoder(x)
        # Only encode (no masking needed for image features)
        memory = self.transformer.encoder(src_pos)
        return memory  # shape: (batch, seq_len, hidden)

    def forward_decoder(self, trg, memory):
        """
        Decodes output tokens using encoder memory. Assumes trg shape: (batch, tgt_seq_len).
        """
        trg_emb = self.decoder(trg)
        trg_pos = self.pos_decoder(trg_emb)
        # Generate mask for autoregressive decoding
        trg_mask = self.generate_square_subsequent_mask(trg.size(1), trg.device)
        trg_key_padding_mask = self.make_len_mask(trg)
        # Decoder forward
        output = self.transformer.decoder(
            tgt=trg_pos,
            memory=memory,
            tgt_mask=trg_mask,
            tgt_key_padding_mask=trg_key_padding_mask,
        )
        output = self.fc_out(output)
        return output
