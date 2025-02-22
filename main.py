# -*- coding: utf-8 -*-
from __future__ import print_function
import os
import time

import numpy as np
import math
from models.Wavenet import Wavenet
from utils.data_utils import *
from utils.math_utils import *
from utils.tester import model_inference
import torchvision
import torch
import torch.optim as optim
import torch.nn as nn
from torch.autograd import Variable
import argparse

np.random.seed(1337)  # for reproducibility

torch.backends.cudnn.benchmark = True


batch_size = 8  # batch size
test_batch_size = 48

lr = 0.0001  # learning rate


parser = argparse.ArgumentParser()
parser.add_argument('--version', type=int, default=0)
parser.add_argument('--model', type=str, default='wavenet')
parser.add_argument('--mode', type=str, default='train')
parser.add_argument('--snorm', type=int, default=1)
parser.add_argument('--tnorm', type=int, default=1)
parser.add_argument('--n_his', type=int, default=16)
parser.add_argument('--n_pred', type=int, default=3)
parser.add_argument('--n_layers', type=int, default=4)
parser.add_argument('--hidden_channels', type=int, default=16)
args = parser.parse_args()

snorm_bool = bool(args.snorm)
tnorm_bool = bool(args.tnorm)
n_his = args.n_his
n_pred = args.n_pred
n_layers = args.n_layers
hidden_channels = args.hidden_channels
version = args.version


def train(model, dataset, n):
    target_n = "s{}_t{}_hc{}_l{}_his{}_pred{}_v{}".format(args.snorm, args.tnorm, args.hidden_channels, n_layers, n_his, n_pred, args.version)
    target_fname = '{}_{}'.format(args.model, target_n)
    target_model_path = os.path.join('MODEL', '{}.h5'.format(target_fname))
    print('=' * 10)
    print("training model...")

    print("releasing gpu memory....")
    model.train()
    criterion = nn.MSELoss()
    optimizer = optim.Adam(filter(lambda p: p.requires_grad, model.parameters()), lr=lr)
    torch.cuda.empty_cache()

    min_rmse = 1000
    min_val = min_va_val = np.array([4e1, 1e5, 1e5] * 3)
    stop = 0
    nb_epoch = 1000

    for epoch in range(nb_epoch):  # loop over the dataset multiple times
        model.train()
        for j, x_batch in enumerate(gen_batch(dataset.get_data('train'), batch_size, dynamic_batch=True, shuffle=True)):
            xh = x_batch[:, 0: n_his]
            y = x_batch[:, n_his:n_his + n_pred]
            xh = torch.tensor(xh, dtype=torch.float32).cuda()
            y = torch.tensor(y, dtype=torch.float32).cuda()
            model.zero_grad()
            pred = model(xh)
            loss = criterion(pred, y)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 10)
            optimizer.step()
        if epoch % 10 == 0:
            model.eval()
            min_va_val, min_val = model_inference(model, dataset, test_batch_size, n_his, n_pred, min_va_val, min_val, n)
            print(f'Epoch {epoch}:')
            va, te = min_va_val, min_val
            for i in range(n_pred):
                print(f'MAPE {va[i*3]:7.3%}, {te[i*3]:7.3%};'
                    f'MAE  {va[i*3+1]:4.3f}, {te[i*3+1]:4.3f};'
                    f'RMSE {va[i*3+2]:6.3f}, {te[i*3+2]:6.3f}.')

            total_rmse = np.sum([va[i*3+2] for i in range(n_pred)])
            if total_rmse < min_rmse:
                torch.save(model.state_dict(), target_model_path)
                min_rmse = total_rmse
                stop = 0
            else:
                stop += 1
            if stop == 5:
                break
    model.load_my_state_dict(torch.load(target_model_path))
    min_va_val, min_val = model_inference(model, dataset, test_batch_size, n_his, n_pred, min_va_val, min_val, n)
    va, te = min_va_val, min_val
    print('Best Results:')
    for i in range(n_pred):
        print(f'MAPE {va[i*3]:7.3%}, {te[i*3]:7.3%};'
            f'MAE  {va[i*3+1]:4.3f}, {te[i*3+1]:4.3f};'
            f'RMSE {va[i*3+2]:6.3f}, {te[i*3+2]:6.3f}.')


def eval(model, dataset, n, versions):
    print('=' * 10)
    print("evaluating model...")
    vas = []
    tes = []
    for _v in versions:
        min_val = min_va_val = np.array([4e1, 1e5, 1e5] * 3)
        target_n = "s{}_t{}_hc{}_l{}_his{}_pred{}_v{}".format(args.snorm, args.tnorm, args.hidden_channels, n_layers, n_his, n_pred, _v)
        target_fname = '{}_{}'.format(args.model, target_n)
        target_model_path = os.path.join('MODEL', '{}.h5'.format(target_fname))
        if os.path.isfile(target_model_path):
            model.load_my_state_dict(torch.load(target_model_path))
        else:
            print("file not exist")
            break
        min_va_val, min_val = model_inference(model, dataset, test_batch_size, n_his, n_pred, min_va_val, min_val, n)
        print(f'Version:{_v}')
        va, te = min_va_val, min_val
        print(f'MAPE {va[0]:7.3%}, {te[0]:7.3%};'
            f'MAE  {va[1]:4.3f}, {te[1]:4.3f};'
            f'RMSE {va[2]:6.3f}, {te[2]:6.3f}.')
        print(f'MAPE {va[3]:7.3%}, {te[3]:7.3%};'
            f'MAE  {va[4]:4.3f}, {te[4]:4.3f};'
            f'RMSE {va[5]:6.3f}, {te[5]:6.3f}.')
        print(f'MAPE {va[6]:7.3%}, {te[6]:7.3%};'
            f'MAE  {va[7]:4.3f}, {te[7]:4.3f};'
            f'RMSE {va[8]:6.3f}, {te[8]:6.3f}.')
        vas.append(va)
        tes.append(te)
    va = np.array(vas).mean(axis=0)
    te = np.array(tes).mean(axis=0)
    print(f'Overall:')
    print(f'MAPE {va[0]:7.3%}, {te[0]:7.3%};'
        f'MAE  {va[1]:4.3f}, {te[1]:4.3f};'
        f'RMSE {va[2]:6.3f}, {te[2]:6.3f}.')
    print(f'MAPE {va[3]:7.3%}, {te[3]:7.3%};'
        f'MAE  {va[4]:4.3f}, {te[4]:4.3f};'
        f'RMSE {va[5]:6.3f}, {te[5]:6.3f}.')
    print(f'MAPE {va[6]:7.3%}, {te[6]:7.3%};'
        f'MAE  {va[7]:4.3f}, {te[7]:4.3f};'
        f'RMSE {va[8]:6.3f}, {te[8]:6.3f}.')


def main():
    # load data
    print("loading data...")
    n_train, n_val, n_test = 78, 7, 7
    n = 336
    n_slots = 24
    dataset = data_gen('data/electricity.csv', (n_train, n_val, n_test), n, n_his + n_pred, n_slots)
    print('=' * 10)
    print("compiling model...")
    model = Wavenet('cuda:0', n, tnorm_bool=tnorm_bool, snorm_bool=snorm_bool, in_dim=1,out_dim=n_pred, channels=hidden_channels, kernel_size=2, blocks=1, layers=n_layers).cuda()


    print('=' * 10)
    print("init model...")
    for p in model.parameters():
        if p.dim() > 1:
            nn.init.xavier_uniform_(p)
        else:
            nn.init.uniform_(p)

    if args.mode == 'train':
        train(model, dataset, n)
    if args.mode == 'eval':
        eval(model, dataset, n, [0, 1, 2, 3, 4, 5])

if __name__ == '__main__':
    main()
