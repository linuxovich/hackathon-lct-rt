import torch
from torch.utils.data import Dataset
from torch.nn.utils.rnn import pad_sequence
from torchvision import transforms
import numpy as np
import cv2

class TextCollate:
    """
    A custom collate function for padding variable-length text sequences.
    This function pads text labels to the max length in a batch and stacks images.
    """
    def __init__(self, pad_token_id=0):
        self.pad_token_id = pad_token_id

    def __call__(self, batch):
        # `batch` is a list of tuples, e.g., [(image, label), (image, label), ...]
        images = [item[0] for item in batch]
        labels = [item[1] for item in batch]

        # Pad labels to the max length within the batch
        # We assume the pad token ID is 0.
        labels_padded = pad_sequence(labels, batch_first=True, padding_value=self.pad_token_id)
        
        # Stack images into a single tensor
        images_stacked = torch.stack(images, dim=0)
        
        return images_stacked, labels_padded

class TextLoader(Dataset):
    def __init__(self, image_paths, labels, hp, p2idx=None, eval=False):
        self.image_paths = image_paths
        self.labels = labels
        self.hp = hp
        self.p2idx = p2idx
        self.eval = eval

        # Define separate transformation pipelines for training and evaluation
        self.transform_train = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((int(hp.height * 1.05), int(hp.width * 1.05))),
            transforms.RandomCrop((hp.height, hp.width)),
            transforms.RandomRotation(degrees=(-2, 2), fill=255),
            transforms.ToTensor(),
            # Use standard ImageNet normalization for pretrained ResNet weights
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        
        self.transform_eval = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((hp.height, hp.width)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])

    def __getitem__(self, index):
        # Read image with OpenCV
        img = cv2.imread(self.image_paths[index], cv2.IMREAD_GRAYSCALE)
        
        # Convert grayscale to 3-channel if necessary
        if img.ndim == 2:
            img = np.stack([img] * 3, axis=-1)
        
        # Apply the appropriate transformation based on mode (train or eval)
        if not self.eval:
            img = self.transform_train(img)
        else:
            img = self.transform_eval(img)
            
        # Process the label
        label_text = self.labels[index]
        label_encoded = [self.p2idx['SOS']] + [self.p2idx[c] for c in label_text if c in self.p2idx] + [self.p2idx['EOS']]
        
        return img, torch.LongTensor(label_encoded)

    def __len__(self):
        return len(self.labels)
