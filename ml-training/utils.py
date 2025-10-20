import os
import cv2
import numpy as np
from os.path import join
from collections import Counter
from tqdm import tqdm
import editdistance

def process_texts(image_dir, trans_dir, hp):
    lens, lines, names = [], [], []
    letters = ''
    all_word = {}
    all_files = os.listdir(trans_dir)
    for filename in tqdm(sorted(os.listdir(image_dir)), desc="Extracting Data (Vocab & Filenames)"):
        if filename[:-3]+'txt' in all_files:
            name, _ = os.path.splitext(filename)
            txt_filepath = join(trans_dir, name + '.txt')
            with open(txt_filepath, 'r', encoding="utf-8") as file:
                data = file.read()
                data = data.replace("i", "и").replace("I", "И").replace("ё", "е").replace("Ё", "Е")
                eng2rus = {
                    'o': 'о', 'a': 'а', 'c': 'с', 'e': 'е', 'p': 'р', 'x': 'х', 'k': 'к',
                    'O': 'О', 'A': 'А', 'C': 'С', 'E': 'Е', 'P': 'Р', 'X': 'Х', 'K': 'К',
                    'і': 'и', 'ї': 'и', 'ѣ': 'ъ', '‐': '-', '—': '-', 'Ï': "И", "ë": "е",
                    "ï": "и", "І": "И", "Ї": "И", "Ѳ": "Ф", "‘": '"', "’": '"', "„": '"',
                    "«": '"', "»": '"', "'": '"'
                }
                data = ''.join([eng2rus.get(char, char) for char in data])
                if len(data) == 0:
                    continue
                if len(set(data).intersection(hp.del_sym)) > 0:
                    continue
                lines.append(data)
                names.append(filename)
                lens.append(len(data))
                letters += data
    words = letters.split()
    for word in words:
        if word not in all_word:
            all_word[word] = 0
        else:
            all_word[word] += 1
    cnt = Counter(letters)
    print('Максимальная длина строки:', max(Counter(lens).keys()))
    return names, lines, cnt, all_word

def text_to_labels(s, p2idx):
    return [p2idx['SOS']] + [p2idx[i] for i in s if i in p2idx.keys()] + [p2idx['EOS']]

def labels_to_text(s, idx2p):
    S = "".join([idx2p[i] for i in s])
    return S if 'EOS' not in S else S[:S.find('EOS')]

def phoneme_error_rate(p_seq1, p_seq2):
    p_vocab = set(p_seq1 + p_seq2)
    p2c = dict(zip(p_vocab, range(len(p_vocab))))
    c_seq1 = [chr(p2c[p]) for p in p_seq1]
    c_seq2 = [chr(p2c[p]) for p in p_seq2]
    return editdistance.eval(''.join(c_seq1), ''.join(c_seq2))

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

def generate_data(names, image_dir):
    return [os.path.join(image_dir, name) for name in tqdm(names)]

def count_parameters(model):
    return sum(p.numel() for p in model.parameters() if p.requires_grad)