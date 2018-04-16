#!/usr/bin/env python3

import time
from functools import reduce
import operator

from utils import *

import gym_duckietown
from gym_duckietown.envs import SimpleSimEnv

import numpy as np

import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.autograd import Variable

def initWeights(m):
    classname = m.__class__.__name__
    if classname.startswith('Conv'):
        nn.init.orthogonal(m.weight.data)
        m.bias.data.fill_(0)
    elif classname.find('Linear') != -1:
        nn.init.xavier_uniform(m.weight)
        m.bias.data.fill_(0)
    elif classname.find('BatchNorm') != -1:
        m.weight.data.normal_(1.0, 0.02)
        m.bias.data.fill_(0)

class Model(nn.Module):
    def __init__(self):
        super().__init__()

        BOTTLENECK_SIZE = 8

        self.conv1 = nn.Conv2d(3, 32, 8, stride=8)
        self.conv2 = nn.Conv2d(32, 32, 4, stride=1)
        self.conv3 = nn.Conv2d(32, 32, 4, stride=1)

        self.linear1 = nn.Linear(32 * 9 * 14, 256)
        self.linear2 = nn.Linear(256, BOTTLENECK_SIZE)
        self.linear3 = nn.Linear(BOTTLENECK_SIZE, 256)
        self.linear4 = nn.Linear(256, 32 * 9 * 14)

        self.deconv1 = nn.ConvTranspose2d(32, 32, 4, stride=1)
        self.deconv2 = nn.ConvTranspose2d(32, 32, 4, stride=1)
        self.deconv3 = nn.ConvTranspose2d(32, 3, 8, stride=8)

        self.a_linear1 = nn.Linear(BOTTLENECK_SIZE, 32)
        self.a_linear2 = nn.Linear(32, 1)

        self.apply(initWeights)

    def forward(self, image):
        batch_size = image.size(0)

        x = image

        x = self.conv1(x)
        x = F.leaky_relu(x)

        x = self.conv2(x)
        x = F.leaky_relu(x)

        x = self.conv3(x)
        conv_out = F.leaky_relu(x)
        conv_out = conv_out.view(batch_size, -1)
        #print(x.size())

        x = F.leaky_relu(self.linear1(conv_out))
        mid = F.leaky_relu(self.linear2(x))
        x = F.leaky_relu(self.linear3(mid))
        x = F.leaky_relu(self.linear4(x))
        x = x.view(batch_size, 32, 9, 14)

        x = self.deconv1(x)
        x = F.leaky_relu(x)

        x = self.deconv2(x)
        x = F.leaky_relu(x)

        x = self.deconv3(x)
        x = F.leaky_relu(x)

        a = F.leaky_relu(self.a_linear1(mid))
        a = self.a_linear2(a)

        return x, a, mid

    def getAngle(self, obs):
        obs = np.ascontiguousarray(obs)
        obs = obs.transpose(2, 0, 1)
        obs = torch.from_numpy(obs).float()
        obs = Variable(obs).unsqueeze(0)

        recon, angle = self(obs)

        return angle.data[0].numpy()

    def printInfo(self):
        modelSize = 0
        for p in self.parameters():
            pSize = reduce(operator.mul, p.size(), 1)
            modelSize += pSize
        print(str(self))
        print('Total model size: %d' % modelSize)

    def save(self, file_name):
        torch.save(self.state_dict(), file_name)

    def load(self, file_name):
        self.load_state_dict(torch.load(file_name))

def genData():
    img = env.reset().copy()
    img = img.transpose(2, 0, 1)

    angle = env.get_follow_angle(0.30)

    return img, angle

def genBatch(batch_size=2):
    imgs = []
    targets = []

    for i in range(0, batch_size):
        img, angle = genData()
        imgs.append(img)
        targets.append(angle)

    imgs = np.stack(imgs)
    targets = np.stack(targets)

    return imgs, targets

def train(model, optimizer, image, target):
    # Zero the parameter gradients
    optimizer.zero_grad()

    # forward + backward + optimize
    recon, angle, enc = model(image)

    img_loss = (recon - image).norm(2).mean()
    ang_loss = (angle - target).norm(2).mean()
    loss = img_loss + 2 * ang_loss

    loss.backward()
    optimizer.step()

    ang_error = (angle - target).abs().mean()

    return loss.data[0], ang_error.data[0]

if __name__ == "__main__":
    env = SimpleSimEnv()
    env.reset()

    model = Model()
    model.printInfo()

    if torch.cuda.is_available():
        model.cuda()

    # weight_decay is L2 regularization, helps avoid overfitting
    optimizer = optim.Adam(
        model.parameters(),
        lr=0.0005,
        weight_decay=1e-3
    )

    avg_error = 0

    for epoch in range(1, 1000000):
        startTime = time.time()
        images, targets = genBatch()
        images = Variable(torch.from_numpy(images).float())
        targets = Variable(torch.from_numpy(targets).float())
        if torch.cuda.is_available():
            images = images.cuda()
            targets = targets.cuda()
        genTime = int(1000 * (time.time() - startTime))

        startTime = time.time()
        loss, error = train(model, optimizer, images, targets)
        trainTime = int(1000 * (time.time() - startTime))

        avg_error = avg_error * 0.995 + 0.005 * error

        print('gen time: %d ms' % genTime)
        print('train time: %d ms' % trainTime)
        print('epoch %d, loss=%.3f, error=%.3f' % (epoch, loss, avg_error))

        if epoch == 50 or epoch % 1000 == 0:
            img0 = images[0:1]
            out0, ang0, enc = model(img0)
            save_img('img_sim.png', img0)
            save_img('img_recon.png', out0)

            for i in range(0, 200):
                try:
                    img = load_img('real_images/img_%03d.png' % i)
                    out, ang, enc = model(img)
                    save_img('real_images/img_%03d_recon.png' % i, out)
                except Exception as e:
                    print(e)

        if epoch % 1000 == 0:
            model.save('trained_models/angle_model.pt')
