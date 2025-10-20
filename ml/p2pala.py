import os
import numpy as np
import cv2

import torch
from torch.utils.data import DataLoader
import torch.optim as optim

from argparse import Namespace
from collections import OrderedDict

from nn_models import models
from data import dataset
from data import transforms as transforms
from data import imgprocess as dp


def predict_layout(image_basenames_to_images, weights_path="models/weights.pth"):
    """Get P2PaLA layout predictions (baselines and regions) for provided images"""
    opts = Namespace(approx_alg='optimal',
                     batch_size=8, cnn_ngf=64,
                     do_class=True, do_off=True,
                     img_size=np.array([1024, 1280], dtype=np.int32), input_channels=3,
                     line_alg='basic', line_color=128, line_offset=30, line_width=7,
                     max_vertex=30, merge_regions={}, merged_regions={}, min_area=0.01, net_out_type='C',
                     nontext_regions=None, num_segments=4, num_workers=4, out_mode='LR',
                     output_channels=9, pin_memory=False,
                     region_types={'full_page': 'TextRegion', 'paragraph': 'TextRegion', 'marginalia': 'TextRegion',
                                   'page-number': 'TextRegion', 'heading': 'TextRegion', 'header': 'TextRegion',
                                   '': 'TextRegion'},
                     regions=['paragraph', 'marginalia', 'page-number', 'heading', 'header', ''],
                     regions_colors=OrderedDict([('paragraph', 1), ('marginalia', 2), ('page-number', 3),
                                                 ('heading', 4), ('header', 5), ('', 6)]),
                     seed=5, shuffle_data=True)
    torch.manual_seed(opts.seed)
    device = torch.device("cpu")
    nnG = None
    torch.set_default_tensor_type("torch.FloatTensor")

    with torch.no_grad():
        if nnG == None:
            # --- Load Model
            nnG = models.buildUnet(
                opts.input_channels,
                opts.output_channels,
                ngf=opts.cnn_ngf,
                net_type=opts.net_out_type,
                out_mode=opts.out_mode,
            ).to(device)

            state_dict = torch.load(weights_path, map_location=lambda storage, loc: storage)
            nnG.load_state_dict(state_dict)

            if opts.do_off:
                nnG.apply(models.off_dropout)

        else:
            if opts.do_off:
                nnG.apply(models.off_dropout)

        pr_data = dp.htrDataProcess(
            opts,
            build_labels=False
        )

        transform = transforms.build_transforms(opts)

    prod_data = dataset.htrDataset(
        basenames_to_images=image_basenames_to_images, transform=transform, opts=opts
    )

    prod_dataloader = DataLoader(
        prod_data,
        batch_size=opts.batch_size,
        shuffle=opts.shuffle_data,
        num_workers=opts.num_workers,
        pin_memory=opts.pin_memory,
    )

    xml_results = {}
    nnG.eval()
    for pr_batch, sample in enumerate(prod_dataloader):
        
        pr_x = sample["image"].to(device)
        pr_ids = sample["id"]
        pr_y_gen = nnG(pr_x)
        if opts.net_out_type == "C":
            if opts.out_mode == "LR":
                _, pr_l = torch.max(pr_y_gen[0], dim=1, keepdim=True)
                _, pr_r = torch.max(pr_y_gen[1], dim=1, keepdim=True)
                pr_y_gen = torch.cat([pr_l, pr_r], 1)
            elif opts.out_mode == "L" or opts.out_mode == "R":
                _, pr_y_gen = torch.max(pr_y_gen, dim=1, keepdim=True)
            else:
                pass
        elif opts.net_out_type == "R":
            pass
        else:
            pass
        for idx, data in enumerate(pr_y_gen.data):
            img_name = pr_ids[idx]
            xml_result = pr_data.gen_page(
                img_name,
                image_basenames_to_images[img_name],
                data.numpy(),
                opts.regions,
                approx_alg=opts.approx_alg,
                num_segments=opts.num_segments,
            )
            xml_results[img_name] = xml_result
    return xml_results
