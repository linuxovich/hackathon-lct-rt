import torch
from torch.utils.data import Dataset
from torchvision import transforms
import random
import numpy as np
import cv2

class TextCollate:
    def __call__(self, batch):
        x_padded = []
        max_y_len = max([i[1].size(0) for i in batch])
        y_padded = torch.LongTensor(max_y_len, len(batch))
        y_padded.zero_()
        for i in range(len(batch)):
            x_padded.append(batch[i][0].unsqueeze(0))
            y = batch[i][1]
            y_padded[:y.size(0), i] = y
        x_padded = torch.cat(x_padded)
        return x_padded, y_padded

class TextLoader(Dataset):
    def __init__(self, image_paths, labels, hp, transform=None, p2idx=None, eval=False):
        self.image_paths = image_paths
        self.labels = labels
        self.hp = hp
        self.p2idx = p2idx
        self.eval = eval
        self.transform = transform if transform else transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((int(hp.height*1.05), int(hp.width*1.05))),
            transforms.RandomCrop((hp.height, hp.width)),
            transforms.RandomRotation(degrees=(-2, 2), fill=255),
            transforms.ToTensor()
        ])
     
    def __getitem__(self, index):
        img = cv2.imread(self.image_paths[index], cv2.IMREAD_GRAYSCALE)
        if img.ndim == 2:
            img = np.stack([img]*3, axis=-1)
        if not self.eval:
            img = self.transform(img)
            img = img / img.max()
            img = img ** (random.random()*0.7 + 0.6)
        else:
            img = np.transpose(img, (2, 0, 1))
            img = img / img.max()
        label = self.labels[index]
        label = [self.p2idx['SOS']] + [self.p2idx[c] for c in label if c in self.p2idx] + [self.p2idx['EOS']]
        return (torch.FloatTensor(img), torch.LongTensor(label))

    def __len__(self):
        return len(self.labels)