import torch
from torch import nn, optim

from ..utils import utils
from .conv2d import Conv2d
from .mlp_decoder_three_layers import ThreeLayersDecoder
from ..algo import supervised_algo


class Dann_F_C(nn.Module):
    def __init__(self):
        super().__init__()
        self.device = torch.device("cpu")
        self.conv2d = Conv2d().to(self.device)
        self.decoder = ThreeLayersDecoder(input_size=1152, output_size=10, fc1_size=3072, fc2_size=2048).to(self.device)
        self.optimizer = optim.Adam(list(self.conv2d.parameters()) + list(self.decoder.parameters()), lr=1e-4)
        self.criterion = nn.CrossEntropyLoss()
        self.num_epochs = 10

    def fit_without_adapt(self, source_loader):
        data = {"loader": source_loader}
        network = {
            "decoder": self.decoder,
            "encoder": self.conv2d,
            "optimizer": self.optimizer,
            "criterion": self.criterion
        }
        config = {
            "use_source_loader": True,
            "num_epochs": self.num_epochs
        }
        supervised_algo.fit(data, network, **config)


    def fit_on_target(self, train_target_prime_loader):
        data = {"loader": train_target_prime_loader}
        network = {
            "decoder": self.decoder,
            "encoder": self.conv2d,
            "optimizer": self.optimizer,
            "criterion": self.criterion
        }
        config = {
            "use_source_loader": True,
            "num_epochs": self.num_epochs
        }
        supervised_algo.fit(data, network, **config)

    def forward(self, x):
        return self.decoder(self.conv2d(x))

    def predict(self, x):
        return self.decoder.predict(self.conv2d(x))

    def predict_proba(self, x):
        return self.decoder.predict_proba(self.conv2d(x))
