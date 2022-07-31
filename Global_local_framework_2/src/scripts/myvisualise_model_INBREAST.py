# visualize saliency map predicted from the model
import os
import torch
import pandas as pd
import numpy as np
from torch import dtype, mode
from src.modeling import gmic
from src.utilities.metric import compute_metric
from src.data_loading.data import get_dataloader
import argparse
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from src.utilities import pickling, tools
import cv2
import imageio
from os.path import exists
from PIL import Image
import pdb
import torch.nn.functional as F
import torchvision.ops.boxes as bops
from src.data_loading.datasets import get_dataloaderINBREAST

from torchcam.methods import SmoothGradCAMpp, CAM, ScoreCAM, GradCAM, GradCAMpp, XGradCAM, LayerCAM, SSCAM, ISCAM


def calculate_metrics(box_gt, thresh_values, cam_image, dictres, method='cam'):

    #boxes
    
    #for ii, th in enumerate([0.5, 0.6, 0.7, 0.8, 0.9]):
    for ii, th in enumerate(thresh_values):

        ret,thresh1 = cv2.threshold(cam_image,th,255,cv2.THRESH_BINARY)
        thresh1 = thresh1.astype(np.uint8)
        contours = cv2.findContours(thresh1, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = contours[0] if len(contours) == 2 else contours[1]
        # result = input_img.copy()
        # result = cv2.cvtColor(result,cv2.COLOR_GRAY2RGB).astype('uint8')

        TPS = FPS = 0
        
        for cntr in contours:
            x,y,w,h = cv2.boundingRect(cntr)

            box2 = torch.tensor([[x, y, x+w, y+h]], dtype=torch.float)
            iou = bops.box_iou(box_gt, box2)
            #if iou >= th:
            if iou >= 0.1:
                TPS += 1
            else:
                FPS += 1
        dictres[method][th]['tp']+=TPS
        dictres[method][th]['fp']+=FPS
        if TPS==0:
            dictres[method][th]['fn']+=1

@torch.no_grad()
def test_net(model, loader, device, threshold, output_path, model_path):
    # load val best to test
    model_path = os.path.join(output_path, 'val_best_model.pth')
    model.load_state_dict(torch.load(model_path)['model_state_dict'], strict=True)
    model.eval()
    
    prediction = np.empty(shape=[0, 2], dtype=np.int)
    # for step, (imgs, labels, _) in enumerate(loader):
    for step, (imgs, labels, test_filename, loc) in enumerate(loader):
        # print(f"step {step}")
        imgs, labels = imgs.to(device), labels.to(device)
        y_global, y_local, y_fusion, saliency_map, _, _ = model(imgs)
        # y_global, y_local, y_fusion, saliency_map, y_score, last_feature_map 
        
        y_fusion = y_fusion[:,1:]
        # y_fusion = y_global[:,1:]
        # import pdb; pdb.set_trace()
        
        result = np.concatenate([y_fusion.cpu().data.numpy(), labels.cpu().data.numpy()], axis=1)
        prediction = np.concatenate([prediction, result], axis=0)

    print('==> ### test metric ###')
    total = len(loader.dataset)
    TP, FN, TN, FP, acc, roc_auc = compute_metric(prediction, threshold)
    sensitivity = TP/(TP+FN)
    specificity = TN/(TN+FP)
    print('Total: %d'%(total))
    print('threshold: %.2f --- TP: %d --- FN: %d --- TN: %d --- FP: %d'%(threshold, TP, FN, TN, FP))
    print('acc: %f --- roc_auc: %f --- sensitivity: %f --- specificity: %f'%(acc, roc_auc, sensitivity, specificity))


def alter_visualize_example_git(input_img, gt_mask, saliency_maps, true_segs,
                      patch_locations, patch_img, patch_attentions,
                      save_dir, output_path, filename, parameters,alter_cam_ben, alter_cam_malig, gradcam_ben,gradcam_malig, gradcampp_ben,gradcampp_malig,
                    xgradcam_ben, xgradcam_malig, layercam_ben, layercam_malig , info_cam_ben, info_cam_malig, y_fusion, label_gt, loc, dict_results):
    """
    Function that visualizes the saliency maps for an example
    """
    # colormap lists
    _, _, h, w = saliency_maps.shape
    #_, _, H, W = input_img.shape
    H, W = input_img.shape
    # convert tensor to numpy array
    # input_img = input_img.data.cpu().numpy()

    # set up colormaps for benign and malignant
    alphas = np.abs(np.linspace(0, 0.95, 259))
    alpha_green = plt.cm.get_cmap('Greens')
    alpha_green._init()
    alpha_green._lut[:, -1] = alphas
    alpha_red = plt.cm.get_cmap('Reds')
    alpha_red._init()
    alpha_red._lut[:, -1] = alphas

    # create visualization template
    #total_num_subplots = 11 + parameters["K"]
    
    figure = plt.figure(figsize=(30, 20))
    # input image + segmentation map
    #subfigure = figure.add_subplot(1, total_num_subplots, 1)
    subfigure = figure.add_subplot(3, 8, 1)
    
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    benign_seg, malignant_seg = true_segs
    if benign_seg is not None:
        cm.Greens.set_under('w', alpha=0)
        subfigure.imshow(benign_seg, alpha=0.85, cmap=cm.Greens, clim=[0.0, 1])
    if malignant_seg is not None:
        cm.OrRd.set_under('w', alpha=0)
        subfigure.imshow(malignant_seg, alpha=0.85, cmap=cm.OrRd, clim=[0.0, 1])
    #  y_fusion
    # import pdb; pdb.set_trace()
    if y_fusion[1]>=0.5:
        model_pred = "M"
        prob = y_fusion[1]
    else:
        model_pred = "B"
        prob = y_fusion[0]
    subfigure.set_title("({}-{:.2f}/{:.2f}".format(model_pred,y_fusion[0],y_fusion[1]))
    subfigure.axis('off')

    #gt_mask

    subfigure = figure.add_subplot(3, 8, 2)
    im2 = input_img.copy()
    im2 = cv2.cvtColor(im2,cv2.COLOR_GRAY2RGB).astype('uint8')
    # import pdb; pdb.set_trace()
    if loc != None:
        #color = (255, 255, 255)
        color = (0, 255, 0)
        # import pdb; pdb.set_trace()
        #im2 = cv2.rectangle(im2, (loc[['xmin']],loc['ymin']), (loc['xmax'],loc['ymax']), color, 5)
        im2 = cv2.rectangle(im2, (int(loc[0].item()),int(loc[1].item())), (int(loc[2].item()),int(loc[3].item())), color, 7)

    
    subfigure.imshow(im2, aspect='equal')
    

    # patch map
    # subfigure = figure.add_subplot(1, total_num_subplots,3)
    subfigure = figure.add_subplot(3, 8, 3)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    cm.YlGnBu.set_under('w', alpha=0)
    crop_mask = tools.get_crop_mask(
        patch_locations[0, np.arange(parameters["K"]), :],
        parameters["crop_shape"], (H, W),
        "upper_left")
    subfigure.imshow(crop_mask, alpha=0.7, cmap=cm.YlGnBu, clim=[0.9, 1])
    if benign_seg is not None:
        cm.Greens.set_under('w', alpha=0)
        subfigure.imshow(benign_seg, alpha=0.85, cmap=cm.Greens, clim=[0.9, 1])
    if malignant_seg is not None:
        cm.OrRd.set_under('w', alpha=0)
        subfigure.imshow(malignant_seg, alpha=0.85, cmap=cm.OrRd, clim=[0.9, 1])
    subfigure.set_title("patch map")
    subfigure.axis('off')

    # class activation maps
    # subfigure = figure.add_subplot(1, total_num_subplots, 5)
    subfigure = figure.add_subplot(3, 8, 9)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    resized_cam_malignant = cv2.resize(saliency_maps[0,1,:,:], (W, H))
    #subfigure.imshow(resized_cam_malignant, cmap=alpha_red, clim=[0.0, 1.0])
    resized_cam_malignant_norm = (resized_cam_malignant- resized_cam_malignant.min())/resized_cam_malignant.max()
    #subfigure.imshow(resized_cam_malignant, cmap=alpha_red, clim=[0.0, 1.0])
    subfigure.imshow(resized_cam_malignant_norm, cmap=alpha_red, clim=[0.0, 1.0])
    # subfigure.imshow(resized_cam_malignant_norm, cmap=alpha_red, clim=[0.5, 1.0])
    subfigure.set_title("SM: malignant")
    subfigure.axis('off')

    ## ALT SM MALIGN
    # subfigure = figure.add_subplot(1, total_num_subplots, 6)
    subfigure = figure.add_subplot(3, 8, 10)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    #resized_cam_malignant = cv2.resize(saliency_maps[0,1,:,:], (W, H))
    # import pdb;pdb.set_trace()
    resized_cam_malignant2 = cv2.resize(alter_cam_malig[0,:,:], (W, H))
    resized_cam_malignant2_norm = (resized_cam_malignant2- resized_cam_malignant2.min())/resized_cam_malignant2.max()
    #subfigure.imshow(resized_cam_malignant, cmap=alpha_red, clim=[0.0, 1.0])
    #subfigure.imshow(resized_cam_malignant2, cmap=alpha_red, clim=[0.0, 1.0])
    subfigure.imshow(resized_cam_malignant2_norm, cmap=alpha_red, clim=[0.0, 1.0])
    # subfigure.imshow(resized_cam_malignant2, cmap=alpha_red, clim=[0.5, 1.0])
    subfigure.set_title("altSM: malignant")
    subfigure.axis('off')

    ## GRAD CAM MALIGN
    subfigure = figure.add_subplot(3, 8, 11)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    #resized_cam_malignant = cv2.resize(saliency_maps[0,1,:,:], (W, H))
    resized_gradcam_malig = cv2.resize(gradcam_malig[0,:,:], (W, H))
    resized_gradcam_malig_norm = (resized_gradcam_malig- resized_gradcam_malig.min())/resized_gradcam_malig.max()
    #subfigure.imshow(resized_cam_malignant, cmap=alpha_red, clim=[0.0, 1.0])
    subfigure.imshow(resized_gradcam_malig_norm, cmap=alpha_red, clim=[0.0, 1.0])
    # subfigure.imshow(resized_gradcam_malig, cmap=alpha_red, clim=[0.5, 1.0])
    subfigure.set_title("gradcam: malign")
    subfigure.axis('off')

    ## GRAD CAM++ MALIGN
    subfigure = figure.add_subplot(3, 8, 12)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    #resized_cam_malignant = cv2.resize(saliency_maps[0,1,:,:], (W, H))
    resized_gradcampp_malig = cv2.resize(gradcampp_malig[0,:,:], (W, H))
    resized_gradcampp_malig_norm = (resized_gradcampp_malig- resized_gradcampp_malig.min())/resized_gradcampp_malig.max()
    #subfigure.imshow(resized_cam_malignant, cmap=alpha_red, clim=[0.0, 1.0])
    subfigure.imshow(resized_gradcampp_malig_norm, cmap=alpha_red, clim=[0.0, 1.0])
    subfigure.set_title("gradcam++: malign")
    subfigure.axis('off')

    ## XGRAD CAM MALIGN
    subfigure = figure.add_subplot(3, 8, 13)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    #resized_cam_malignant = cv2.resize(saliency_maps[0,1,:,:], (W, H))
    resized_xgradcam_malig = cv2.resize(xgradcam_malig[0,:,:], (W, H))
    resized_xgradcam_malig_norm = (resized_xgradcam_malig- resized_xgradcam_malig.min())/resized_xgradcam_malig.max()
    #subfigure.imshow(resized_cam_malignant, cmap=alpha_red, clim=[0.0, 1.0])
    subfigure.imshow(resized_xgradcam_malig_norm, cmap=alpha_red, clim=[0.0, 1.0])
    # subfigure.imshow(resized_gradcam_malig, cmap=alpha_red, clim=[0.5, 1.0])
    subfigure.set_title("XGradCam: malign")
    subfigure.axis('off')

    ## LAYER CAM MALIGN
    subfigure = figure.add_subplot(3, 8, 14)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    #resized_cam_malignant = cv2.resize(saliency_maps[0,1,:,:], (W, H))
    resized_layercam_malig = cv2.resize(layercam_malig[0,:,:], (W, H))
    resized_layercam_malig_norm = (resized_layercam_malig- resized_layercam_malig.min())/resized_layercam_malig.max()
    #subfigure.imshow(resized_cam_malignant, cmap=alpha_red, clim=[0.0, 1.0])
    subfigure.imshow(resized_layercam_malig_norm, cmap=alpha_red, clim=[0.0, 1.0])
    # subfigure.imshow(resized_gradcam_malig, cmap=alpha_red, clim=[0.5, 1.0])
    subfigure.set_title("Layercam: malign")
    subfigure.axis('off')

    ## INFOCAM MALIG
    #subfigure = figure.add_subplot(1, total_num_subplots, 11)
    subfigure = figure.add_subplot(3, 8, 15)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    #resized_cam_malignant = cv2.resize(saliency_maps[0,1,:,:], (W, H))
    resized_infocam_malig = cv2.resize(info_cam_malig[0,:,:], (W, H))
    resized_infocam_malig_norm = (resized_infocam_malig- resized_infocam_malig.min())/resized_infocam_malig.max()
    #subfigure.imshow(resized_cam_malignant, cmap=alpha_red, clim=[0.0, 1.0])
    subfigure.imshow(resized_infocam_malig_norm, cmap=alpha_red, clim=[0.0, 1.0])
    # subfigure.imshow(resized_infocam_malig_norm, cmap=alpha_red, clim=[0.5, 1.0])
    subfigure.set_title("infoCAM: malign")
    subfigure.axis('off')

    ## class activation map - benig
    #subfigure = figure.add_subplot(1, total_num_subplots, 4)
    subfigure = figure.add_subplot(3, 8, 17)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    resized_cam_benign = cv2.resize(saliency_maps[0,0,:,:], (W, H))
    resized_cam_benign_norm = (resized_cam_benign- resized_cam_benign.min())/resized_cam_benign.max()
    #subfigure.imshow(resized_cam_benign, cmap=alpha_green, clim=[0.0, 1.0])
    subfigure.imshow(resized_cam_benign_norm, cmap=alpha_green, clim=[0.0, 1.0])
    # subfigure.imshow(resized_cam_benign_norm, cmap=alpha_green, clim=[0.0, 1.0])
    subfigure.set_title("SM: benign")
    subfigure.axis('off')

     ## ALT SM BENIG
    # subfigure = figure.add_subplot(1, total_num_subplots, 6)
    subfigure = figure.add_subplot(3, 8, 18)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    #resized_cam_malignant = cv2.resize(saliency_maps[0,1,:,:], (W, H))
    # import pdb;pdb.set_trace()
    resized_cam_benig = cv2.resize(alter_cam_ben[0,:,:], (W, H))
    #subfigure.imshow(resized_cam_malignant, cmap=alpha_red, clim=[0.0, 1.0])
    subfigure.imshow(resized_cam_benig, cmap=alpha_red, clim=[0.0, 1.0])
    # subfigure.imshow(resized_cam_benig, cmap=alpha_red, clim=[0.5, 1.0])
    subfigure.set_title("altSM: benig")
    subfigure.axis('off')

    ## GRAD CAM BENIG
    subfigure = figure.add_subplot(3, 8, 19)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    #resized_cam_malignant = cv2.resize(saliency_maps[0,1,:,:], (W, H))
    resized_gradcam_ben = cv2.resize(gradcam_ben[0,:,:], (W, H))
    #subfigure.imshow(resized_cam_malignant, cmap=alpha_red, clim=[0.0, 1.0])
    #subfigure.imshow(resized_gradcam_ben, cmap=alpha_red, clim=[0.0, 1.0])
    subfigure.imshow(resized_gradcam_ben, cmap=alpha_red, clim=[0.5, 1.0])
    subfigure.set_title("gradcam: benig")
    subfigure.axis('off')

    ## GRAD CAM++ BENIG
    subfigure = figure.add_subplot(3, 8, 20)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    #resized_cam_malignant = cv2.resize(saliency_maps[0,1,:,:], (W, H))
    resized_gradcam_ben = cv2.resize(gradcampp_ben[0,:,:], (W, H))
    #subfigure.imshow(resized_cam_malignant, cmap=alpha_red, clim=[0.0, 1.0])
    subfigure.imshow(resized_gradcam_ben, cmap=alpha_red, clim=[0.0, 1.0])
    # subfigure.imshow(resized_gradcam_ben, cmap=alpha_red, clim=[0.5, 1.0])
    subfigure.set_title("gradcam++: benig")
    subfigure.axis('off')

    ## XGRAD CAM BENIG
    subfigure = figure.add_subplot(3, 8, 21)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    #resized_cam_malignant = cv2.resize(saliency_maps[0,1,:,:], (W, H))
    resized_gradcam_benig = cv2.resize(xgradcam_ben[0,:,:], (W, H))
    #subfigure.imshow(resized_cam_malignant, cmap=alpha_red, clim=[0.0, 1.0])
    subfigure.imshow(resized_gradcam_benig, cmap=alpha_red, clim=[0.0, 1.0])
    # subfigure.imshow(resized_gradcam_benig, cmap=alpha_red, clim=[0.5, 1.0])
    subfigure.set_title("XGradCam: benig")
    subfigure.axis('off')

    ## LAYER CAM BENIG
    subfigure = figure.add_subplot(3, 8, 22)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    #resized_cam_malignant = cv2.resize(saliency_maps[0,1,:,:], (W, H))
    resized_gradcam_ben = cv2.resize(layercam_ben[0,:,:], (W, H))
    #subfigure.imshow(resized_cam_malignant, cmap=alpha_red, clim=[0.0, 1.0])
    subfigure.imshow(resized_gradcam_ben, cmap=alpha_red, clim=[0.0, 1.0])
    # subfigure.imshow(resized_gradcam_ben, cmap=alpha_red, clim=[0.5, 1.0])
    subfigure.set_title("Layercam: benig")
    subfigure.axis('off')

    ## INFOCAM BENIG
    #subfigure = figure.add_subplot(1, total_num_subplots, 11)
    subfigure = figure.add_subplot(3, 8, 23)
    #subfigure.imshow(input_img[0, 0, :, :], aspect='equal', cmap='gray')
    subfigure.imshow(input_img, aspect='equal', cmap='gray')
    #resized_cam_malignant = cv2.resize(saliency_maps[0,1,:,:], (W, H))
    resized_infocam_ben = cv2.resize(info_cam_ben[0,:,:], (W, H))
    resized_infocam_benig_norm = (resized_infocam_ben- resized_infocam_ben.min())/resized_infocam_ben.max()
    #subfigure.imshow(resized_cam_malignant, cmap=alpha_red, clim=[0.0, 1.0])
    subfigure.imshow(resized_infocam_benig_norm, cmap=alpha_red, clim=[0.0, 1.0])
    # subfigure.imshow(resized_infocam_benig_norm, cmap=alpha_red, clim=[0.5, 1.0])
    subfigure.set_title("infoCAM: benig")
    subfigure.axis('off')

    

    # crops
    # for crop_idx in range(parameters["K"]):
    #     subfigure = figure.add_subplot(3, 8, 4+crop_idx)
    #     subfigure.imshow(patch_img[0, crop_idx, :, :], cmap='gray', alpha=.8, interpolation='nearest',
    #                      aspect='equal')
    #     subfigure.axis('off')
    #     # crops_attn can be None when we only need the left branch + visualization
    #     subfigure.set_title("$\\alpha_{0} = ${1:.2f}".format(crop_idx, patch_attentions[crop_idx]))
    # plt.savefig(save_dir, bbox_inches='tight', format="png", dpi=500)
    # plt.close()


    # get contours
    # gt_xmin = gt_ymin = gt_xmax = gt_ymax = 0
    # if loc != None:
    #     # (loc[['xmin']],loc['ymin']), (loc['xmax'],loc['ymax']), color, 5)
    #     gt_xmin, gt_ymin, gt_xmax, gt_ymax = int(loc[0].item()),int(loc[1].item()), int(loc[2].item()),int(loc[3].item())
    

    # figure = plt.figure(figsize=(30, 20))
    # subfigure = figure.add_subplot(2, 6, 1)
    # subfigure.imshow(input_img, aspect='equal', cmap='gray')
    # subfigure.imshow(resized_cam_malignant_norm, cmap=alpha_red, clim=[0.0, 1.0])
    # subfigure.set_title("original: cam_malig")
    # # import pdb; pdb.set_trace()

    # #boxes
    # box_gt = torch.tensor([[gt_xmin,gt_ymin, gt_xmax, gt_ymax]], dtype=torch.float)
    
    # thresh_values=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
    # # methods=['cam','gradcam','gradcam++','xgradcam','layercam','infocam']
    # calculate_metrics(box_gt, thresh_values, resized_cam_malignant_norm, dict_results, method='cam')
    # calculate_metrics(box_gt, thresh_values, resized_gradcam_malig_norm, dict_results, method='gradcam')
    # calculate_metrics(box_gt, thresh_values, resized_gradcampp_malig_norm, dict_results, method='gradcam++')
    # calculate_metrics(box_gt, thresh_values, resized_xgradcam_malig_norm, dict_results, method='xgradcam')
    # calculate_metrics(box_gt, thresh_values, resized_layercam_malig_norm, dict_results, method='layercam')
    # calculate_metrics(box_gt, thresh_values, resized_infocam_malig_norm, dict_results, method='infocam')

    # #for ii, th in enumerate(thresh_values):
    # for ii, th in enumerate([0.5, 0.6, 0.7, 0.8, 0.9]):

    #     subfigure = figure.add_subplot(2, 6, ii+2)
    #     #subfigure.imshow(resized_cam_malignant_norm>0.5, cmap=alpha_red, clim=[0.0, 1.0])
    #     subfigure.imshow(resized_cam_malignant_norm>th, cmap=alpha_red, clim=[0.0, 1.0])
    #     #subfigure.set_title("th=0.5")
    #     subfigure.set_title(f"th={th}")

    #     ret,thresh1 = cv2.threshold(resized_cam_malignant_norm,th,255,cv2.THRESH_BINARY)
    #     thresh1 = thresh1.astype(np.uint8)
    #     contours = cv2.findContours(thresh1, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    #     contours = contours[0] if len(contours) == 2 else contours[1]
    #     result = input_img.copy()
    #     result = cv2.cvtColor(result,cv2.COLOR_GRAY2RGB).astype('uint8')

    #     TPS = FPS = 0
        
    #     for cntr in contours:
    #         x,y,w,h = cv2.boundingRect(cntr)

    #         box2 = torch.tensor([[x, y, x+w, y+h]], dtype=torch.float)
    #         iou = bops.box_iou(box_gt, box2)
    #         #if iou >= th:
    #         if iou >= 0.1:
    #             TPS += 1
    #         else:
    #             FPS += 1

    #         # import pdb; pdb.set_trace()
    #         cv2.rectangle(result, (x, y), (x+w, y+h), (255, 0, 0), 6)
    #         cv2.rectangle(result, (gt_xmin,gt_ymin), (gt_xmax, gt_ymax), (0, 255, 0), 6)
    #         cv2.putText(result, f"{iou.item():.2}", (x, y-4), cv2.FONT_HERSHEY_SIMPLEX, 
    #                3, (255, 0, 0), 5, cv2.LINE_AA)
    #         # print("x,y,w,h:",x,y,w,h)
    #     subfigure = figure.add_subplot(2, 6, 6+ii+2)
    #     # subfigure.imshow(result, cmap='gray')
    #     subfigure.imshow(result, aspect='equal')
    #     subfigure.set_title(F"tp={TPS}, fp={FPS}")

    # subfigure = figure.add_subplot(2, 6, 7)
    # # subfigure.imshow(result, cmap='gray')
    # subfigure.imshow(im2, aspect='equal')
    # subfigure.set_title("boxes")
    # plt.savefig(save_dir[:-4]+'esp'+save_dir[-4:], bbox_inches='tight', format="png", dpi=500)
    # plt.close()

    
#def visualize_saliency_patch_maps(model, output_path, loader, device, test_filename, mask_dir, mode):
#def visualize_saliency_patch_maps(model, output_path, loader, device, mask_dir, mode):
def visualize_saliency_patch_maps(model, output_path, loader, device, mask_dir):
    
    if not os.path.exists(output_path):
        os.mkdir(output_path)

    methods=['cam','gradcam','gradcam++','xgradcam','layercam','infocam']
    thresh_values=[0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 0.95]
    dict_results={'total_mass':0}
    for m in methods:
        dict_results[m]={}
        for t in thresh_values:
            dict_results[m][t]={'tp':0, 'fp':0, 'fn':0, 'tpr':0, 'fppi':0}
    
    for step, (imgs, labels, test_filename, loc) in enumerate(loader):
        imgs, labels = imgs.to(device), labels.to(device)

        
        model.eval()
        

        #GradCam++
        gradcampp_extractor = GradCAMpp(model, target_layer='ds_net.relu') # [works fine]
        #gradcampp_extractor = GradCAMpp(model, target_layer='left_postprocess_net.gn_conv_last') # [works fine]
        # gradcampp_extractor = GradCAMpp(model, target_layer='ds_net.layer_list.4') # [works fine]

        # for name, layer in model.named_modules():
        #     if isinstance(layer, nn.ReLU):
        #         print(name, layer)

        # GradCam
        gradcam__extractor = GradCAM(model, target_layer='ds_net.relu') # [works fine]
        
        #SmoothGradCAMpp
        # gradcampp_extractor = SmoothGradCAMpp(model, target_layer='ds_net.relu')  # [Failed]

        #XgradCam
        xgradcam_extractor = XGradCAM(model, target_layer='ds_net.relu')  # [works fine]
        #xgradcam_extractor = XGradCAM(model, target_layer='left_postprocess_net.gn_conv_last')  # [works fine]
        # xgradcam_extractor = XGradCAM(model, target_layer='ds_net.layer_list.4')  # [works fine]

        #LayerCam
        layercam_extractor = LayerCAM(model, target_layer=['ds_net.layer_list.4','ds_net.layer_list.3']) # [works fine, but need to change extractor]
        # layercam_extractor = LayerCAM(model, target_layer=['dn_resnet.layer4','dn_resnet.layer3']) # [works fine, but need to change extractor]


        #GradCAMpp
        # cam_extractor = CAM(model, target_layer='ds_net.layer_list.4')
        #cam_extractor = CAM(model, fc_layer='left_postprocess_net.gn_conv_last',target_layer='ds_net.layer_list.4')
        #cam_extractor = CAM(model, fc_layer='left_postprocess_net.gn_conv_last')

        #CAM
        cam_extractor = CAM(model, fc_layer='left_postprocess_net.gn_conv_last',target_layer='ds_net.relu')  # [works fine]
        # cam_extractor = CAM(model, fc_layer='left_postprocess_net.gn_conv_last',target_layer='left_postprocess_net.gn_conv_last')  # [works fine]

        
        y_global, y_local, y_fusion, saliency_map, y_score, last_feature_map = model(imgs)


       
        # cam_extractor = CAM(model, fc_layer='left_postprocess_net.gn_conv_last')
        saliency_maps = model.saliency_map.data.cpu().numpy()

        #InfoCAM
        
        # batch, channel, _, _ = last_feature_map.size()
        # _, target = y_score.topk(1, 1, True, True)
        # target = target.squeeze()
        # _, top_2_target = y_score.topk(2, 1, True, True)

        # fc_weight = model.global_network.postprocess_module.gn_conv_last.weight
        # target_2 = top_2_target[:, -1]
        # cam_weight = fc_weight[target]

        # cam_weight_2 = fc_weight[target_2]
        # cam_weight = cam_weight - cam_weight_2

        # cam_weight = cam_weight.view(batch, channel, 1, 1).expand_as(last_feature_map)
        # cam_info = (cam_weight * last_feature_map)

        # cam_filter = torch.ones(1, channel, 3, 3).to(target.device)
        # cam_info = F.conv2d(cam_info, cam_filter, padding=2, stride=1)
        cam_info=None

        
        patch_locations = model.patch_locations
        patch_imgs = model.patches
        # patch_attentions = model.patch_attns[0, :].data.cpu().numpy()
        patch_attentions = model.patch_attns.data.cpu().numpy()
        batch_size = imgs.size()[0]

        

        # dict_results={'cam':{'tp':0, 'fp':0, 'tn':0, 'total_mass':0},
        #                 'gradcam':{'tp':0, 'fp':0, 'tn':0, 'total_mass':0},
        # }

        # model.zero_grad()
        # y_global, y_local, y_fusion, saliency_map, y_score, last_feature_map = model(imgs)

        for i in range(batch_size):
        # save_dir = os.path.join("visualization", "{0}.png".format(short_file_path))

            # possui massa
            if labels[i].item()==1:

                #dict_results['cam']['total_mass'] += 1
                dict_results['total_mass'] += 1

                filename = test_filename[i]
                print(step, i)
                print(filename)
                # if "MERGED" in filename:
                #     continue
                #filename = filename[filename.find('/')+1:filename.find('.')]
                filename = filename.split('/')[-1]
                #save_dir = os.path.join(output_path, "{}.png".format(filename))
                save_dir = os.path.join(output_path, filename)
                print('processing {}'.format(filename))
                #===========================================================================
                # load segmentation if available
                # benign_seg_path = os.path.join(mask_dir, "{0}_{1}".format(filename, "benign.png"))
                malignant_seg_path = os.path.join(mask_dir, "{0}_{1}".format(filename, "malignant.png"))
                benign_seg = None
                malignant_seg = None
                # if os.path.exists(benign_seg_path):
                #     mask_image = np.array(imageio.imread(benign_seg_path))
                #     benign_seg = mask_image.astype(np.float32)
                if os.path.exists(malignant_seg_path):
                    mask_image = np.array(imageio.imread(malignant_seg_path))
                    malignant_seg = mask_image.astype(np.float32)
                #=========================================================================
                        
                # visualize_example(imgs[i:i+1,:,:,:], saliency_maps[i:i+1,:,:,:], [benign_seg, malignant_seg],
                #         patch_locations[i:i+1,:,:], patch_imgs[i:i+1,:,:,:], patch_attentions[i],
                #         save_dir, parameters, mode)

                
                    
                
                #img = np.array(Image.open(test_filename[i]), dtype=np.float32)
                img = Image.open(test_filename[i])
                
                # gt_mask_path = test_filename[i].replace('full','merged_masks').replace("FULL","MASK_1")
                # print(gt_mask_path)
                # if exists(gt_mask_path) ==False:
                #     continue
                #     gt_mask_path = gt_mask_path.replace("1","MERGED")
                # gt_mask = Image.open(gt_mask_path)
                #img = img.resize((2944, 1920))
                img = img.resize((1920, 2944))
                # gt_mask = gt_mask.resize((1920, 2944))
                img = np.array(img, dtype=np.float32)
                # gt_mask = np.array(gt_mask, dtype=np.float32)
                # view = filename.rsplit('-', 2)[1].split('_')[2]
                # if view == 'R':
                #     img = np.fliplr(img)
                #     gt_mask = np.fliplr(gt_mask)
                # import pdb; pdb.set_trace()

                # if "RIGHT" in test_filename[i]:  
                #     img = np.fliplr(img)
                #     gt_mask = np.fliplr(gt_mask)
                # visualize_example_git(imgs[i:i+1,:,:,:], saliency_maps[i:i+1,:,:,:], [benign_seg, malignant_seg],
                #         patch_locations[i:i+1,:,:], patch_imgs[i:i+1,:,:,:], patch_attentions[i],
                #         save_dir, parameters)

                
                
                ## CAM extractor
                alter_cam_malig = cam_extractor(1)[0][i:i+1,:,:]
                # alter_cam_malig = cam_extractor(1, scores=y_score)[0][i:i+1,:,:]  # ScoreCAM
                alter_cam_malig = alter_cam_malig.data.cpu().numpy()

                alter_cam_ben = cam_extractor(0)[0][i:i+1,:,:]
                alter_cam_ben = alter_cam_ben.data.cpu().numpy()

                # alter_cam_malig=None
                # alter_cam_ben=None

                ## INFOCAM ##
                # info_cam_malig = cam_info[i].data.cpu().numpy()
                # info_cam_ben = cam_info[i].data.cpu().numpy()
                #temporary (just to test)
                info_cam_malig = alter_cam_malig
                info_cam_ben = alter_cam_malig

                

                ## GRADCAM EXTRACTOR ##
                gradcam_ben = gradcam__extractor(class_idx=0, scores=y_score)[0][i:i+1,:,:]
                # import pdb; pdb.set_trace()
                gradcam_ben = gradcam_ben.data.cpu().numpy()
                gradcam_malig = gradcam__extractor(class_idx=1, scores=y_score)[0][i:i+1,:,:]
                gradcam_malig = gradcam_malig.data.cpu().numpy()
                
                
                ## GRADCAMPP EXTRACTOR ##
                gradcampp_ben = gradcampp_extractor(class_idx=0, scores=y_score)[0][i:i+1,:,:]    
                gradcampp_ben = gradcampp_ben.data.cpu().numpy()
                gradcampp_malig = gradcampp_extractor(class_idx=1, scores=y_score)[0][i:i+1,:,:] 
                gradcampp_malig = gradcampp_malig.data.cpu().numpy()

                ## XGRADCAM EXTRACTOR
                xgradcam_ben = xgradcam_extractor(class_idx=0, scores=y_score)[0][i:i+1,:,:]
                xgradcam_ben = xgradcam_ben.data.cpu().numpy()
                xgradcam_malig = xgradcam_extractor(class_idx=1, scores=y_score)[0][i:i+1,:,:]
                xgradcam_malig = xgradcam_malig.data.cpu().numpy()
                # import pdb; pdb.set_trace()


                # LAYER CAM EXTRACTOR
                # alter_gradcam_ben = gradcampp_extractor(class_idx=0, scores=y_score)[0][i:i+1,:,:]
                cams  = layercam_extractor(class_idx=0, scores=y_score)
                # import pdb; pdb.set_trace()
                layercam_ben = layercam_extractor.fuse_cams(cams)[i:i+1,:,:]
                layercam_ben = layercam_ben.data.cpu().numpy()

                cams  = layercam_extractor(class_idx=1, scores=y_score)
                layercam_malig = layercam_extractor.fuse_cams(cams)[i:i+1,:,:]
                layercam_malig= layercam_malig.data.cpu().numpy()
                

                #alter_gradcam_malig = gradcampp_extractor(class_idx=1, scores=y_global)[0][i:i+1,:,:]
                
                #alter_gradcam_malig = gradcampp_extractor(class_idx=1, scores=y_score)[0][i:i+1,:,:]
                # alter_gradcam_malig = gradcampp_extractor(class_idx=1, scores=y_score)
                # alter_gradcam_malig = extractor.fuse_cams(alter_gradcam_malig)
                # alter_gradcam_malig = alter_gradcam_malig.data.cpu().numpy()
                
                # import pdb; pdb.set_trace()
                # visualize_example_git(img, saliency_maps[i:i+1,:,:,:], [benign_seg, malignant_seg],
                #         patch_locations[i:i+1,:,:], patch_imgs[i:i+1,:,:,:], patch_attentions[i],
                #         save_dir, parameters)
                # import pdb; pdb.set_trace()
                gt_mask=None

                alter_visualize_example_git(img, gt_mask, saliency_maps[i:i+1,:,:,:], [benign_seg, malignant_seg],
                        patch_locations[i:i+1,:,:], patch_imgs[i:i+1,:,:,:], patch_attentions[i],
                        save_dir, output_path, filename, parameters, alter_cam_ben, alter_cam_malig, gradcam_ben,gradcam_malig, gradcampp_ben,gradcampp_malig,
                        xgradcam_ben, xgradcam_malig, layercam_ben, layercam_malig , info_cam_ben, info_cam_malig, y_fusion[i], labels[i], (loc['xmin'][i],loc['ymin'][i],loc['xmax'][i],loc['ymax'][i]), 
                        dict_results)

    
    # for m in methods:
    #     # dict_results[m]={}
    #     for t in thresh_values:
    #         #dict_results[m][t]={'tp':0, 'fp':0, 'tn':0, 'tpr':0, 'fppi':0}
    #         dict_results[m][t]['tpr']=dict_results[m][t]['tp']/(dict_results[m][t]['tp']+dict_results[m][t]['fn'])
    #         dict_results[m][t]['fppi']=dict_results[m][t]['fp']/dict_results['total_mass']
    # print(dict_results)
    # file_results = open(os.path.join(output_path,'metrics.txt'),'w')
    # file_results.write(f"Total Mass Images: {dict_results['total_mass']}\n\n")
    # for m in methods:
    #     file_results.write(f"{m}:\n")
    #     for t in thresh_values:
    #         file_results.write(f"\tth = {t}\n")
    #         file_results.write(F"\t\tTP = {dict_results[m][t]['tp']}\tFP={dict_results[m][t]['fp']}\tFN={dict_results[m][t]['fn']}\tTPR = {dict_results[m][t]['tpr']}\tFPPI={dict_results[m][t]['fppi']}\n")
    # file_results.close()
        

             

if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument("--model_path", type=str, default='models/sample_model_1.p',
        help="pretrained model path")
    # ap.add_argument("--data_csv_path", type=str, default='data/cropped_mammo-16/test.csv',
    #     help="test data csv path")
    ap.add_argument("--data_path", type=str, default='data/cropped_mammo-16/test',
        help="test data path")
    ap.add_argument("--bs", type=int, default=6,
        help="batch size")
    ap.add_argument("--num_chan", type=int, default=3,
        help="batch size")
    ap.add_argument("--is", type=int, default=(2944, 1920),
        help="image size")
    ap.add_argument("--percent_t", type=float, default=0.02,
        help="percent for top-T pooling")
    ap.add_argument("--mask_dir", type=str, default='data/mammo-test-samples/segmentation', 
        help='mask directory')
    ap.add_argument("--output_path", type=str, default='retrained_visualization', 
        help='visualization directory')
    ap.add_argument("--mammo_sample_data", type=bool, default=False,
        help="whether visualise the provided sample data")
    ap.add_argument("--pretrained_model", type=bool, default=False,
        help="whether use pretrained_model")
    ap.add_argument("--gpuid", type=int, default=0,
        help="gpu id")
    ap.add_argument("--v1_global", type=bool, default=False,
        help="use RN18 as v1_global")
    ap.add_argument("--kvalue", type=int, default=6,
        help="kvalue")
    
    args = vars(ap.parse_args())

   
    # Test_data = args['data_csv_path']
    DATA_PATH = args['data_path']
    num_works = 4

    device_type = 'gpu'
    # device_type = 'cpu'
    gpu_id = args['gpuid']
    
    threshold = 0.5
    model_path = args['model_path']
    # beta = args['beta']
    beta = 3.259162430057801e-06
    percent_t = args['percent_t']

    img_size = args['is']
    batch_size = args['bs']
    # aug = args['aug']
    aug = False
    pretrained_model = args['pretrained_model']
    use_v1_global = args['v1_global']
        
    max_value=65535

    parameters = {
        "device_type": device_type,
        "gpu_number": gpu_id,
        "max_crop_noise": (100, 100),
        "max_crop_size_noise": 100,
        # model related hyper-parameters
        "percent_t": percent_t,
        "cam_size": (46, 30),
        #"K": 6,
        "K": args['kvalue'],
        "crop_shape": (256, 256),
        "use_v1_global":use_v1_global
    }

    if use_v1_global:
        parameters["cam_size"] = (92, 60)

    torch.manual_seed(1)
    torch.cuda.manual_seed(1)
    # import pdb; pdb.set_trace()
    model = gmic.GMIC(parameters)
    if device_type == 'gpu' and torch.has_cudnn:
        device = torch.device("cuda:{}".format(gpu_id))
        if pretrained_model:
            model.load_state_dict(torch.load(model_path), strict=False)
            
            # model.load_state_dict(torch.load(model_path)['model_state_dict'], strict=True)
        else:
            model.load_state_dict(torch.load(model_path)['model_state_dict'], strict=True)
            # pass
            
        
    # else:
    #     if pretrained_model:
    #         #model.load_state_dict(torch.load(model_path, map_location="cpu"), strict=False)
    #         model.load_state_dict(torch.load(model_path, map_location="cpu"), strict=True)
    #     else:
    #         # model.load_state_dict(torch.load((model_path)['model_state_dict'],  map_location="cpu"), strict=True)
    #         pass
    #     device = torch.device("cpu")
    model = model.to(device)
    # model = torch.nn.DataParallel(model)

    params = [p for p in model.parameters() if p.requires_grad]

    # test_loader = get_dataloader(os.path.join(DATA_PATH, 'test'), Test_data, image_size=img_size, batch_size=batch_size, shuffle=False, \
    #     max_value=max_value)
    #test_loader = get_dataloaderCBIS(os.path.join(DATA_PATH, 'test'), image_size=img_size, batch_size=batch_size, shuffle=False, max_value=max_value, aug=aug)
    test_loader = get_dataloaderINBREAST(DATA_PATH, 'test', image_size=img_size, batch_size=batch_size, shuffle=False, max_value=max_value, aug=aug, num_chan=args['num_chan'])
    
    
    output_path = args['output_path'] 


    if pretrained_model:
        #visualize_saliency_patch_maps(model, output_path, test_loader, device, test_filename, mask_dir)
        visualize_saliency_patch_maps(model = model, output_path=output_path, loader=test_loader, device=device, mask_dir=args['mask_dir'])
        
    else:
        #visualize_saliency_patch_maps(model, output_path, test_loader, device, test_filename, mask_dir)
        visualize_saliency_patch_maps(model = model, output_path=output_path, loader=test_loader, device=device, mask_dir=args['mask_dir'])
        # test_net(model=model, loader=test_loader, device=device, threshold=threshold, output_path=output_path, model_path=model_path)
        