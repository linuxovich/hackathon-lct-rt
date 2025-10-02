from __future__ import print_function
from __future__ import division

import os

import numpy as np
import torch
from torch.utils.data import Dataset

# from torchvision import transforms
import cv2

# from scipy.ndimage.interpolation import map_coordinates
# from scipy.ndimage.filters import gaussian_filter
import logging

try:
    import cPickle as pickle
except:
    import pickle  # --- To handle data imports/export


class htrDataset(Dataset):
    """
    Class to handle HTR dataset feeding
    """

    def __init__(self, basenames_to_images, label_lst=None, transform=None, logger=None, opts=None):
        """
        Args:
            img_lst (string): Path to the list of images to be processed
            label_lst (string): Path to the list of label files to be processed
            transform (callable, optional): Optional transform to be applied
                on a sample.
        """
        self.logger = logger or logging.getLogger(__name__)
        self.transform = transform
        # --- save all paths into a single dic

        self.img_paths_and_images = basenames_to_images

        self.build_label = False
        # --- Labels will be loaded only if label_lst exists
        if label_lst != None:
            self.label_paths = open(label_lst, "r").readlines()
            self.label_paths = [x.rstrip() for x in self.label_paths]
            self.build_label = True
            # --- pre-compute per class weigths
            # --- one count is added per class in order to avoid zero prob.
            # --- weights will be restrict to the interval [1/log(1+c), 1/log(c)]
            # --- for the default c=1.02 => [50.49,1.42]
            temp_index = np.indices(opts.img_size)
            if opts.out_mode == "LR":
                self.w = [
                    np.ones(2, dtype=np.float),
                    np.ones(len(opts.regions) + 1, dtype=np.float),
                ]
                self.prior = [
                    np.zeros((2, opts.img_size[0], opts.img_size[1]), dtype=np.float),
                    np.zeros(
                        (len(opts.regions) + 1, opts.img_size[0], opts.img_size[1]),
                        dtype=np.float,
                    ),
                ]
                for l in self.label_paths:
                    with open(l, "rb") as fh:
                        label = pickle.load(fh)
                    self.w[0] += np.bincount(label[0].flatten(), minlength=2)
                    self.prior[0][tuple((label[0], temp_index[0], temp_index[1]))] += 1
                    self.w[1] += np.bincount(
                        label[1].flatten(), minlength=len(opts.regions) + 1
                    )
                    self.prior[1][tuple((label[1], temp_index[0], temp_index[1]))] += 1
                self.w[0] = self.w[0] / (
                    (len(self.label_paths) * opts.img_size.sum()) + 2
                )
                self.w[1] = self.w[1] / (
                    (len(self.label_paths) * opts.img_size.sum())
                    + len(opts.regions)
                    + 1
                )
                self.w[0] = 1 / np.log(opts.weight_const + self.w[0])
                self.w[1] = 1 / np.log(opts.weight_const + self.w[1])
                self.prior[0] += np.finfo(float).eps
                self.prior[0] = self.prior[0] / self.prior[0].sum(axis=0)[None, :, :]
                self.prior[1] += np.finfo(float).eps
                self.prior[1] = self.prior[1] / self.prior[1].sum(axis=0)[None, :, :]
        self.img_ids = list(self.img_paths_and_images.keys())
        self.opts = opts

    def __len__(self):
        return len(self.img_paths_and_images)

    def __getitem__(self, idx):
        image = list(self.img_paths_and_images.values())[idx]
        # --- swap color axis because
        # --- cv2 image: H x W x C
        # --- torch image: C X H X W
        # ---Keep arrays on float32 format for GPU compatibility
        # --- Normalize to [-1,1] range
        # --- TODO: Move norm comp and transforms to GPU
        if not self.build_label:
            # --- resize image in-situ, so no need to save it to disk
            image = cv2.resize(
                image,
                (self.opts.img_size[1], self.opts.img_size[0]),
                interpolation=cv2.INTER_CUBIC,
            )

        image = (((2 / 255) * image.transpose((2, 0, 1))) - 1).astype(np.float32)
        if self.build_label:
            fh = open(self.label_paths[idx], "rb")
            label = pickle.load(fh)
            # --- TODO: change to opts.net+out_type == C
            if self.opts.do_class:
                # --- convert labels to np.int for compatibility to NLLLoss
                label = label.astype(np.int)
            else:
                # --- norm to [-1,1]
                label = (((2 / 255) * label) - 1).astype(np.float32)
                # --- force array to be a 3D tensor as needed by conv2d
                if label.ndim == 2:
                    label = np.expand_dims(label, 0)
            fh.close()
            sample = {"image": image, "label": label, "id": self.img_ids[idx]}
        else:
            sample = {"image": image, "id": self.img_ids[idx]}
        if self.transform:
            sample = self.transform(sample)

        return sample
