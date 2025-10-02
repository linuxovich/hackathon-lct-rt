from __future__ import print_function
from __future__ import division
from builtins import range

# import os
import math

import numpy as np
import torch

# from torch.utils.data import Dataset
from torchvision import transforms as tv_transforms

# import cv2
from scipy.ndimage.interpolation import map_coordinates
from scipy.ndimage.interpolation import affine_transform
from scipy.ndimage.filters import gaussian_filter

# import logging


def build_transforms(opts):
    tr = []
    # --- transform data(ndarrays) to tensor
    tr.append(toTensor())
    # --- Normalize to 0-mean, 1-var
    tr.append(normalizeTensor(mean=None, std=None))
    # --- add all trans to que tranf queue
    return tv_transforms.Compose(tr)


class toTensor(object):
    """Convert dataset sample (ndarray) to tensor"""

    def __call__(self, sample):
        # for k, v in sample.iteritems():
        for k, v in list(sample.items()):
            if type(v) is np.ndarray:
                # --- by default float arrays will be converted to float tensors
                # --- and int arrays to long tensor.
                sample[k] = torch.from_numpy(v)
        return sample


class normalizeTensor(object):
    """Normalize tensor to given meand and std, or its mean and std per 
    channel"""

    def __init__(self, mean=None, std=None):
        self.mean = mean
        self.std = std

    def __call__(self, sample):
        if torch.is_tensor(sample["image"]):
            if self.mean is None or self.std is None:
                self.mean = []
                self.std = []
                for t in sample["image"]:
                    self.mean.append(t.mean())
                    self.std.append(t.std())
            if (
                not len(self.mean) == sample["image"].shape[0]
                or not len(self.std) == sample["image"].shape[0]
            ):
                raise ValueError(
                    "mean and std size must be equal to the number of channels of the input tensor."
                )
            for i, t in enumerate(sample["image"]):
                t.sub_(self.mean[i]).div_(self.std[i])
        else:
            raise TypeError(
                "Input image is not a tensor, make sure to queue this after toTensor transform"
            )
        return sample


