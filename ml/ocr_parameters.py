import cv2
import numpy as np


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
    if S.find('EOS') == -1:
        return S
    else:
        return S[:S.find('EOS')]


def process_image(img, hp):
    img = np.stack([img, img, img], axis=-1)
    w, h, _ = img.shape

    new_w = hp.height
    new_h = int(h * (new_w / w))
    img = cv2.resize(img, (new_h, new_w))
    w, h, _ = img.shape

    img = img.astype('float32')
    new_h = hp.width
    if h < new_h:
        add_zeros = np.full((w, new_h - h, 3), 255)
        img = np.concatenate((img, add_zeros), axis=1)
    if h > new_h:
        img = cv2.resize(img, (new_h, new_w))
    return img
