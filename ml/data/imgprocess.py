from __future__ import print_function
from __future__ import division

import os
import glob
import logging
import errno
import sys
import string
import random

import numpy as np
import cv2

from shapely.geometry import LineString

try:
    import cPickle as pickle
except:
    import pickle  # --- To handle data export

from page_xml.xmlPAGE import pageData
from utils import polyapprox as pa



class htrDataProcess:
    """
    """

    def __init__(self, opts, build_labels=True):
        """ function to proces all data into a htr dataset"""
        # --- file formats from opencv imread supported formats
        # --- any issue see: https://docs.opencv.org/3.0-beta/modules/imgcodecs/doc/reading_and_writing_images.html#imread
        self.formats = ["tif", "tiff", "png", "jpg", "jpeg", "JPG", "bmp"]
        self.build_labels = build_labels
        self.opts = opts
        self.do_class = opts.net_out_type == "C"
        self.line_color = 1 if opts.do_class else opts.line_color
        self.validValues = string.ascii_uppercase + string.ascii_lowercase + string.digits
        if self.opts.out_mode == "L":
            self.th_span = 64
        else:
            if len(self.opts.regions_colors.keys()) > 1:
                self.th_span = (
                    self.opts.regions_colors[list(self.opts.regions_colors.keys())[1]]
                    - self.opts.regions_colors[list(self.opts.regions_colors.keys())[0]]
                ) / 2
            else:
                self.th_span = 64

    def gen_page(
        self,
        img_name,
        img,
        data,
        reg_list=None,
        approx_alg=None,
        num_segments=None,
    ):
        """
        """
        lines_image = data[0].astype(np.uint8) * 255
        self.approx_alg = self.opts.approx_alg if approx_alg == None else approx_alg
        self.num_segments = (
            self.opts.num_segments if num_segments == None else num_segments
        )
        # --- sym link to original image

        (o_rows, o_cols, _) = img.shape
        o_max = max(o_rows, o_cols)
        o_min = min(o_rows, o_cols)
        cScale = np.array(
            [o_cols / self.opts.img_size[1], o_rows / self.opts.img_size[0]]
        )

        page = pageData(
            os.path.join(img_name, "page", img_name + ".xml")
        )

        page.new_page(img_name, str(o_rows), str(o_cols))
        ####
        if self.opts.net_out_type == "C":
            if self.opts.out_mode == "L":
                lines = data[0].astype(np.uint8)
                reg_list = ["full_page"]
                colors = {"full_page": 0}
                r_data = np.zeros(lines.shape, dtype=np.uint8)
            elif self.opts.out_mode == "R":
                r_data = data[0]
                lines = np.zeros(r_data.shape, dtype=np.uint8)
                colors = self.opts.regions_colors
            elif self.opts.out_mode == "LR":
                lines = data[0].astype(np.uint8)
                #lines = data[0]
                r_data = data[1]
                colors = self.opts.regions_colors
            else:
                pass
        elif self.opts.net_out_type == "R":
            if self.opts.out_mode == "L":
                l_color = (-1 - ((self.line_color * (2 / 255)) - 1)) / 2
                lines = np.zeros(data[0].shape, dtype=np.uint8)
                lines[data[0] >= l_color] = 1
                reg_list = ["full_page"]
                colors = {"full_page": 128}
                r_data = np.zeros(lines.shape, dtype=np.uint8)
            elif self.opts.out_mode == "R":
                r_data = data[1]
                colors = self.opts.regions_colors
                lines = np.zeros(r_data.shape, dtype=np.uint8)
            elif self.opts.out_mode == "LR":
                l_color = (-1 - ((self.line_color * (2 / 255)) - 1)) / 2
                lines = np.zeros(data[0].shape, dtype=np.uint8)
                lines[data[0] >= l_color] = 1
                r_data = data[1]
                colors = self.opts.regions_colors
            else:
                pass
        else:
            pass
        reg_mask = np.zeros(r_data.shape, dtype="uint8")
        lin_mask = np.zeros(lines.shape, dtype="uint8")
        r_id = 0
        kernel = np.ones((5, 5), np.uint8)

        # --- get regions and lines for each class
        for reg in reg_list:
            r_color = colors[reg]
            r_type = self.opts.region_types[reg]

            # --- fill the array is faster then create a new one or mult by 0
            reg_mask.fill(0)
            if self.opts.net_out_type == "R":
                lim_inf = ((r_color - self.th_span) * (2 / 255)) - 1
                lim_sup = ((r_color + self.th_span) * (2 / 255)) - 1
                reg_mask[np.where((r_data > lim_inf) & (r_data < lim_sup))] = 1
            elif self.opts.net_out_type == "C":
                reg_mask[r_data == r_color] = 1
            else:
                pass

            #_, contours, hierarchy = cv2.findContours(
            #    reg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            #)

            res_ = cv2.findContours(
                reg_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
            )
            
            if len(res_) == 2:
                contours, hierarchy = res_
            else:
                _, contours, hierarchy = res_
            
            for cnt in contours:
                # --- remove small objects
                if cnt.shape[0] < 4:
                    continue
                if cv2.contourArea(cnt) < self.opts.min_area * self.opts.img_size[0]:
                    continue

                rect = cv2.minAreaRect(cnt)
                # --- soft a bit the region to prevent spikes
                epsilon = 0.005 * cv2.arcLength(cnt, True)
                approx = cv2.approxPolyDP(cnt, epsilon, True)
                # box = np.array((rect[0][0], rect[0][1], rect[1][0], rect[1][1])).astype(int)
                r_id = r_id + 1
                approx = (approx * cScale).astype("int32")
                reg_coords = ""
                for x in approx.reshape(-1, 2):
                    reg_coords = reg_coords + " {},{}".format(x[0], x[1])

                if (
                    self.opts.nontext_regions == None
                    or reg not in self.opts.nontext_regions
                ):
                    # --- get lines inside the region
                    lin_mask.fill(0)

                    if not self.opts.out_mode == "R" and self.opts.line_alg != "external":
                        cv2.fillConvexPoly(lin_mask, points=cnt, color=(1, 1, 1))
                        lin_mask = cv2.erode(lin_mask, kernel, iterations=1)
                        lin_mask = cv2.dilate(lin_mask, kernel, iterations=1)
                        reg_lines = lines * lin_mask
                        # --- search for the lines
                        #_, l_cont, l_hier = cv2.findContours(
                        #    reg_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                        #)
                        
                        resl_ = cv2.findContours(
                            reg_lines, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
                        )
                        
                        if len(resl_) ==2:
                            l_cont, l_hier = resl_
                        else:
                            _, l_cont, l_hier = resl_
                        
                        
                        if len(l_cont) == 0:
                            continue
                        # --- Add region to XML only is there is some line
                        uuid = ''.join(random.choice(self.validValues) for _ in range(4))
                        text_reg = page.add_element(
                            r_type, "r" + uuid + "_" +str(r_id), reg, reg_coords.strip()
                        )
                        n_lines = 0
                        for l_id, l_cnt in enumerate(l_cont):
                            if l_cnt.shape[0] < 4:
                                continue
                            if cv2.contourArea(l_cnt) < 0.01 * self.opts.img_size[0]:
                                continue
                            # --- convert to convexHull if poly is not convex
                            if not cv2.isContourConvex(l_cnt):
                                l_cnt = cv2.convexHull(l_cnt)
                            lin_coords = ""
                            l_cnt = (l_cnt * cScale).astype("int32")
                            (is_line, approx_lin) = self._get_baseline(img, l_cnt)
                            if is_line == False:
                                continue
                            is_line, l_cnt = build_baseline_offset(
                                approx_lin, offset=self.opts.line_offset
                            )
                            if is_line == False:
                                continue
                            for l_x in l_cnt.reshape(-1, 2):
                                lin_coords = lin_coords + " {},{}".format(
                                    l_x[0], l_x[1]
                                )
                            uuid = ''.join(random.choice(self.validValues) for _ in range(4))
                            text_line = page.add_element(
                                "TextLine",
                                "l" + uuid + "_" + str(l_id),
                                reg,
                                lin_coords.strip(),
                                parent=text_reg,
                            )
                            baseline = pa.points_to_str(approx_lin)
                            page.add_baseline(baseline, text_line)
                            n_lines += 1
                        # --- remove regions without text lines
                        if n_lines == 0:
                            page.remove_element(text_reg)
                    else:
                        uuid = ''.join(random.choice(self.validValues) for _ in range(4))
                        text_reg = page.add_element(
                            r_type, "r" + uuid + "_" + str(r_id), reg, reg_coords.strip()
                        )
                else:
                    uuid = ''.join(random.choice(self.validValues) for _ in range(4))
                    text_reg = page.add_element(
                        r_type, "r" + uuid + "_" + str(r_id), reg, reg_coords.strip()
                    )

        return page.get_content()

    def _get_baseline(self, Oimg, Lpoly):
        """
        """
        # --- Oimg = image to find the line
        # --- Lpoly polygon where the line is expected to be
        minX = Lpoly[:, :, 0].min()
        maxX = Lpoly[:, :, 0].max()
        minY = Lpoly[:, :, 1].min()
        maxY = Lpoly[:, :, 1].max()
        mask = np.zeros(Oimg.shape, dtype=np.uint8)
        cv2.fillConvexPoly(mask, Lpoly, (255, 255, 255))
        res = cv2.bitwise_and(Oimg, mask)
        bRes = Oimg[minY:maxY, minX:maxX]
        bMsk = mask[minY:maxY, minX:maxX]
        if not all(bRes.shape):
            return (False, [[0, 0]])
        bRes = cv2.cvtColor(bRes, cv2.COLOR_RGB2GRAY)
        _, bImg = cv2.threshold(bRes, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        _, cols = bImg.shape
        # --- remove black halo around the image
        bImg[bMsk[:, :, 0] == 0] = 255
        Cs = np.cumsum(abs(bImg - 255), axis=0)
        maxPoints = np.argmax(Cs, axis=0)
        Lmsk = np.zeros(bImg.shape)
        points = np.zeros((cols, 2), dtype="int")
        # --- gen a 2D list of points
        for i, j in enumerate(maxPoints):
            points[i, :] = [i, j]
        # --- remove points at post 0, those are very probable to be blank columns
        points2D = points[points[:, 1] > 0]
        if points2D.size <= 15:
            # --- there is no real line
            return (False, [[0, 0]])
        if self.approx_alg == "optimal":
            # --- take only 100 points to build the baseline
            if points2D.shape[0] > self.opts.max_vertex:
                points2D = points2D[
                    np.linspace(
                        0, points2D.shape[0] - 1, self.opts.max_vertex, dtype=np.int
                    )
                ]
            (approxError, approxLin) = pa.poly_approx(
                points2D, self.num_segments, pa.one_axis_delta
            )
        elif self.approx_alg == "trace":
            approxLin = pa.norm_trace(points2D, self.num_segments)
        else:
            approxLin = points2D
        approxLin[:, 0] = approxLin[:, 0] + minX
        approxLin[:, 1] = approxLin[:, 1] + minY
        return (True, approxLin)


# ---- misc functions to this class


def build_baseline_offset(baseline, offset=50):
    """
    build a simple polygon of width $offset around the
    provided baseline, 75% over the baseline and 25% below.
    """
    try:
        line = LineString(baseline)
        up_offset = line.parallel_offset(offset * 0.75, "right", join_style=2)
        bot_offset = line.parallel_offset(offset * 0.25, "left", join_style=2)
    except:
        #--- TODO: check if this baselines can be saved
        return False, None
    if (
        up_offset.type != "LineString"
        or up_offset.is_empty == True
        or bot_offset.type != "LineString"
        or bot_offset.is_empty == True
    ):
        return False, None
    else:
        up_offset = np.array(up_offset.coords).astype(np.int)
        bot_offset = np.array(bot_offset.coords).astype(np.int)
        return True, np.vstack((up_offset, bot_offset))
