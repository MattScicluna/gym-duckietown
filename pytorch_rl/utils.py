import torch
import torch.nn as nn


# Necessary for my KFAC implementation.
class AddBias(nn.Module):
    def __init__(self, bias):
        super(AddBias, self).__init__()
        self._bias = nn.Parameter(bias.unsqueeze(1))

    def forward(self, x):
        if x.dim() == 2:
            bias = self._bias.t().view(1, -1)
        else:
            bias = self._bias.t().view(1, -1, 1, 1)

        return x + bias

# A temporary solution from the master branch.
# https://github.com/pytorch/pytorch/blob/7752fe5d4e50052b3b0bbc9109e599f8157febc0/torch/nn/init.py#L312
# Remove after the next version of PyTorch gets release.
def orthogonal(tensor, gain=1):
    if tensor.ndimension() < 2:
        raise ValueError("Only tensors with 2 or more dimensions are supported")

    rows = tensor.size(0)
    cols = tensor[0].numel()
    flattened = torch.Tensor(rows, cols).normal_(0, 1)

    if rows < cols:
        flattened.t_()

    # Compute the qr factorization
    q, r = torch.qr(flattened)
    # Make Q uniform according to https://arxiv.org/pdf/math-ph/0609050.pdf
    d = torch.diag(r, 0)
    ph = d.sign()
    q *= ph.expand_as(q)

    if rows < cols:
        q.t_()

    tensor.view_as(q).copy_(q)
    tensor.mul_(gain)
    return tensor



from collections import OrderedDict
import _pickle as pickle
import inspect
import os
import torch
from torch.autograd import Variable
import torch.optim as optim
import numpy as np


#### ------------------------------------------------------------------------------------------ ####
# Below code is modified from https://github.com/apsarath/myTorch/blob/master/myTorch/utils/utils.py 

class MyContainer():

    def __init__(self):
        self.__dict__['tparams'] = OrderedDict()

    def __setattr__(self, name, array):
        tparams = self.__dict__['tparams']
        tparams[name] = array

    def __setitem__(self, name, array):
        self.__setattr__(name, array)

    def __getitem__(self, name):
        return self.__getattr__(name)

    def __getattr__(self, name):
        tparams = self.__dict__['tparams']
        if name in tparams:
            return tparams[name]
        else:
            return None

    def remove(self, name):
        del self.__dict__['tparams'][name]

    def get(self):
        return self.__dict__['tparams']

    def values(self):
        tparams = self.__dict__['tparams']
        return list(tparams.values())

    def save(self, filename):
        tparams = self.__dict__['tparams']
        pickle.dump({p: tparams[p] for p in tparams}, open(filename, 'wb'), 2)

    def load(self, filename):
        tparams = self.__dict__['tparams']
        loaded = pickle.load(open(filename, 'rb'))
        for k in loaded:
            tparams[k] = loaded[k]

    def setvalues(self, values):
        tparams = self.__dict__['tparams']
        for p, v in zip(tparams, values):
            tparams[p] = v

    def __enter__(self):
        _, _, _, env_locals = inspect.getargvalues(inspect.currentframe().f_back)
        self.__dict__['_env_locals'] = list(env_locals.keys())

    def __exit__(self, type, value, traceback):
        _, _, _, env_locals = inspect.getargvalues(inspect.currentframe().f_back)
        prev_env_locals = self.__dict__['_env_locals']
        del self.__dict__['_env_locals']
        for k in list(env_locals.keys()):
            if k not in prev_env_locals:
                self.__setattr__(k, env_locals[k])
                env_locals[k] = self.__getattr__(k)
        return True

def act_name(activation):
    if activation == None:
        return 'linear'
    elif activation == torch.sigmoid:
        return 'sigmoid'
    elif activation == torch.nn.LogSoftmax:
        return 'sigmoid'
    elif activation == torch.tanh:
        return 'tanh'

def create_folder(folder):
    if not os.path.exists(folder):
        os.makedirs(folder)


def my_variable(input, use_gpu=False, volatile=False, requires_grad=True):
    v = Variable(input, volatile=volatile, requires_grad=requires_grad)
    if use_gpu:
        v = v.cuda()
    return v

def modify_config_params(config, config_flag):
    config_flag = config_flag.split("__")
    if len(config_flag) % 2 != 0:
        print("format {config_param1}__{value1}__{config_param2}__{value2} ... ")
        assert(0)

    config_flag_values = [(flag, value) for flag, value in zip(config_flag[::2], config_flag[1::2])]
    for flag, value in config_flag_values:
        if flag in config.get():
            print(("Setting {} with value {}".format(flag, value)))
            if isinstance(config.get()[flag], str):
                config.get()[flag] = value
            else:
                config.get()[flag] = eval(value)
        else:
            assert("Flag {} not present in config !".format(flag))

def one_hot(x, n):
    if isinstance(x, list):
        x = np.array(x)
    x = x.flatten()
    o_h = np.zeros((len(x), n))
    o_h[np.arange(len(x)), x] = 1
    return o_h

def get_optimizer(params, config):
    if config.optim_name == "RMSprop":
        return optim.RMSprop(params, lr=config.lr, alpha=config.alpha, eps=config.eps, weight_decay=config.weight_decay, momentum=config.momentum, centered=config.centered)
    elif config.optim_name == "Adadelta":
        return optim.Adadelta(params, lr=config.lr, rho=config.rho, eps=config.eps, weight_decay=config.weight_decay)
    elif config.optim_name == "Adagrad":
        return optim.Adagrad(params, lr=config.lr, lr_decay=config.lr_decay, weight_decay=config.weight_decay)
    elif config.optim_name == "Adam":
        return optim.Adam(params, lr=config.lr, betas=(config.beta_0, config.beta_1), eps=config.eps, weight_decay=config.weight_decay)
    elif config.optim_name == "SGD":
        return optim.SGD(params, lr=config.lr, momentum=config.momentum, dampening=config.dampening, weight_decay=config.weight_decay, nesterov=config.nesterov)
    else:
        assert("Unsupported optimizer : {}. Valid optimizers : Adadelta, Adagrad, Adam, RMSprop, SGD".format(config.optim_name))