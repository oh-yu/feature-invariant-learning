import numpy as np
import torch
from absl import flags
from torch import nn, optim
from torch.utils.data import DataLoader, TensorDataset

from ..algo import coral_algo, dann_algo, jdot_algo
from ..utils import utils
from .conv1d_three_layers import Conv1dThreeLayers
from .conv1d_two_layers import Conv1dTwoLayers
from .conv2d import Conv2d
from .mlp_decoder_three_layers import ThreeLayersDecoder

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
FLAGS = flags.FLAGS
ALGORYTHMS = {"DANN": dann_algo, "CoRAL": coral_algo, "JDOT": jdot_algo}


class IsihDanns:
    """
    TODO: Attach paper
    """

    def __init__(self, experiment: str):
        assert experiment in ["ECOdataset", "ECOdataset_synthetic", "HHAR", "MNIST"]

        if experiment in ["ECOdataset", "ECOdataset_synthetic"]:
            self.feature_extractor = Conv1dTwoLayers(input_size=3).to(DEVICE)
            self.domain_classifier_dim1 = ThreeLayersDecoder(
                input_size=128, output_size=1, dropout_ratio=0, fc1_size=50, fc2_size=10
            ).to(DEVICE)
            self.task_classifier_dim1 = ThreeLayersDecoder(
                input_size=128, output_size=1, dropout_ratio=0, fc1_size=50, fc2_size=10
            ).to(DEVICE)

            self.feature_optimizer_dim1 = optim.Adam(self.feature_extractor.parameters(), lr=0.0001)
            self.domain_optimizer_dim1 = optim.Adam(self.domain_classifier_dim1.parameters(), lr=0.0001)
            self.task_optimizer_dim1 = optim.Adam(self.task_classifier_dim1.parameters(), lr=0.0001)
            self.criterion = nn.BCELoss()
            self.num_epochs_dim1 = 200

            self.domain_classifier_dim2 = ThreeLayersDecoder(
                input_size=128, output_size=1, dropout_ratio=0, fc1_size=50, fc2_size=10
            ).to(DEVICE)
            self.task_classifier_dim2 = ThreeLayersDecoder(
                input_size=128, output_size=1, dropout_ratio=0, fc1_size=50, fc2_size=10
            ).to(DEVICE)
            self.feature_optimizer_dim2 = optim.Adam(self.feature_extractor.parameters(), lr=0.00005)
            self.domain_optimizer_dim2 = optim.Adam(self.domain_classifier_dim2.parameters(), lr=0.00005)
            self.task_optimizer_dim2 = optim.Adam(self.task_classifier_dim2.parameters(), lr=0.00005)
            self.num_epochs_dim2 = 100
            self.is_target_weights = True

            self.device = DEVICE
            self.stop_during_epochs = False

            self.batch_size = 32
            self.experiment = experiment
            self.do_early_stop = False

        elif experiment == "HHAR":
            self.feature_extractor = Conv1dThreeLayers(input_size=6).to(DEVICE)
            self.domain_classifier_dim1 = ThreeLayersDecoder(input_size=128, output_size=1, dropout_ratio=0.3).to(
                DEVICE
            )
            self.task_classifier_dim1 = ThreeLayersDecoder(input_size=128, output_size=6, dropout_ratio=0.3).to(DEVICE)
            self.feature_optimizer_dim1 = optim.Adam(self.feature_extractor.parameters(), lr=0.0001)
            self.domain_optimizer_dim1 = optim.Adam(self.domain_classifier_dim1.parameters(), lr=0.0001)
            self.task_optimizer_dim1 = optim.Adam(self.task_classifier_dim1.parameters(), lr=0.0001)
            self.criterion = nn.BCELoss()
            self.num_epochs_dim1 = 200

            self.domain_classifier_dim2 = ThreeLayersDecoder(input_size=128, output_size=1, dropout_ratio=0.3).to(
                DEVICE
            )
            self.task_classifier_dim2 = ThreeLayersDecoder(input_size=128, output_size=6, dropout_ratio=0.3).to(DEVICE)

            self.feature_optimizer_dim2 = optim.Adam(self.feature_extractor.parameters(), lr=0.00005)
            self.domain_optimizer_dim2 = optim.Adam(self.domain_classifier_dim2.parameters(), lr=0.00005)
            self.task_optimizer_dim2 = optim.Adam(self.task_classifier_dim2.parameters(), lr=0.00005)
            self.num_epochs_dim2 = 100
            self.is_target_weights = True

            self.device = DEVICE
            self.stop_during_epochs = False
            self.batch_size = 128
            self.experiment = experiment
            self.do_early_stop = False

        elif experiment in ["MNIST"]:
            self.feature_extractor = Conv2d()
            self.task_classifier_dim1 = ThreeLayersDecoder(
                input_size=1152, output_size=10, fc1_size=3072, fc2_size=2048
            )
            self.domain_classifier_dim1 = ThreeLayersDecoder(
                input_size=1152, output_size=1, fc1_size=1024, fc2_size=1024
            )
            self.feature_optimizer_dim1 = optim.Adam(self.feature_extractor.parameters(), lr=0.0001)
            self.domain_optimizer_dim1 = optim.Adam(self.domain_classifier_dim1.parameters(), lr=0.0001)
            self.task_optimizer_dim1 = optim.Adam(self.task_classifier_dim1.parameters(), lr=0.0001)
            self.criterion = nn.BCELoss()
            self.num_epochs_dim1 = 100

            self.task_classifier_dim2 = ThreeLayersDecoder(
                input_size=1152, output_size=10, fc1_size=3072, fc2_size=2048
            )
            self.domain_classifier_dim2 = ThreeLayersDecoder(
                input_size=1152, output_size=1, fc1_size=1024, fc2_size=1024
            )
            self.feature_optimizer_dim2 = optim.Adam(self.feature_extractor.parameters(), lr=1e-4)
            self.domain_optimizer_dim2 = optim.Adam(self.domain_classifier_dim2.parameters(), lr=1e-6)
            self.task_optimizer_dim2 = optim.Adam(self.task_classifier_dim2.parameters(), lr=1e-4)
            self.num_epochs_dim2 = 100
            self.is_target_weights = False

            self.device = torch.device("cpu")
            self.batch_size = 64
            self.experiment = experiment
            self.do_early_stop = False

    def fit_1st_dim(
        self,
        source_ds: torch.utils.data.TensorDataset,
        target_ds: torch.utils.data.TensorDataset,
        test_target_X: torch.Tensor,
        test_target_y_task: torch.Tensor,
    ):
        if FLAGS.is_RV_tuning:
            self._fit_RV_1st_dim(source_ds, target_ds, test_target_X, test_target_y_task)
        else:
            source_loader = DataLoader(source_ds, batch_size=self.batch_size, shuffle=True)
            target_loader = DataLoader(target_ds, batch_size=self.batch_size, shuffle=True)
            self._fit_1st_dim(source_loader, target_loader, test_target_X, test_target_y_task)

    def _fit_RV_1st_dim(
        self,
        source_ds: torch.utils.data.TensorDataset,
        target_ds: torch.utils.data.TensorDataset,
        test_target_X: torch.Tensor,
        test_target_y_task: torch.Tensor,
    ) -> None:
        # 1. split source into train, val
        train_source_loader, val_source_loader = utils.tensordataset_to_splitted_loaders(source_ds, self.batch_size)
        train_target_loader, val_target_loader = utils.tensordataset_to_splitted_loaders(target_ds, self.batch_size)

        # 2. free params
        free_params = [
            {"lr": 0.00001, "eps": 1e-08, "weight_decay": 0},
            {"lr": 0.0001, "eps": 1e-08, "weight_decay": 0},
            {"lr": 0.001, "eps": 1e-08, "weight_decay": 0},
        ]
        RV_scores = {"free_params": [], "scores": []}
        for param in free_params:
            self.__init__(self.experiment)
            self.feature_optimizer_dim1.param_groups[0].update(param)
            self.domain_optimizer_dim1.param_groups[0].update(param)
            self.task_optimizer_dim1.param_groups[0].update(param)
            # 3. RV algo
            ## 3.1 fit f_i
            val_source_X = torch.cat([X for X, _ in val_source_loader], dim=0)
            val_source_y_task = torch.cat([y[:, utils.COL_IDX_TASK] for _, y in val_source_loader], dim=0)
            self.do_early_stop = True
            self._fit_1st_dim(train_source_loader, train_target_loader, val_source_X, val_source_y_task)
            ## 3.2 fit \bar{f}_i
            train_target_X = torch.cat([X for X, _ in train_target_loader], dim=0)
            train_target_pred_y_task = self.predict(train_target_X, is_1st_dim=True)
            val_target_X = torch.cat([X for X, _ in val_target_loader], dim=0)
            val_target_pred_y_task = self.predict(val_target_X, is_1st_dim=True)

            train_target_ds = TensorDataset(
                train_target_X,
                torch.cat(
                    [
                        train_target_pred_y_task.reshape(-1, 1),
                        torch.zeros_like(train_target_pred_y_task).reshape(-1, 1).to(torch.float32),
                    ],
                    dim=1,
                ),
            )
            target_as_source_loader = DataLoader(train_target_ds, batch_size=self.batch_size, shuffle=True)

            train_source_X = torch.cat([X for X, _ in train_source_loader], dim=0)
            train_source_ds = TensorDataset(
                train_source_X, torch.ones(train_source_X.shape[0]).to(torch.float32).to(self.device)
            )
            train_source_as_target_loader = DataLoader(train_source_ds, batch_size=self.batch_size, shuffle=True)

            self.__init__(self.experiment)
            self.feature_optimizer_dim1.param_groups[0].update(param)
            self.domain_optimizer_dim1.param_groups[0].update(param)
            self.task_optimizer_dim1.param_groups[0].update(param)
            self.do_early_stop = True
            self._fit_1st_dim(
                target_as_source_loader, train_source_as_target_loader, val_target_X, val_target_pred_y_task
            )
            ## 3.3 get RV loss
            pred_y_task = self.predict(val_source_X, is_1st_dim=True)
            acc_RV = sum(pred_y_task == val_source_y_task) / val_source_y_task.shape[0]
            RV_scores["free_params"].append(param)
            RV_scores["scores"].append(acc_RV.item())

        # 4. Retraining
        best_param = RV_scores["free_params"][np.argmax(RV_scores["scores"])]
        self.__init__(self.experiment)
        self.feature_optimizer_dim1.param_groups[0].update(best_param)
        self.domain_optimizer_dim1.param_groups[0].update(best_param)
        self.task_optimizer_dim1.param_groups[0].update(best_param)
        source_loader = DataLoader(source_ds, batch_size=self.batch_size, shuffle=True)
        target_loader = DataLoader(target_ds, batch_size=self.batch_size, shuffle=True)
        if self.experiment == "MNIST":
            self.do_early_stop = True
        else:
            self.do_early_stop = False
        self._fit_1st_dim(source_loader, target_loader, val_source_X, val_source_y_task)

    def _fit_1st_dim(self, source_loader, target_loader, test_target_X: torch.Tensor, test_target_y_task: torch.Tensor):
        data = {
            "source_loader": source_loader,
            "target_loader": target_loader,
            "target_X": test_target_X,
            "target_y_task": test_target_y_task,
        }
        if FLAGS.algo_name == "DANN":
            network = {
                "feature_extractor": self.feature_extractor,
                "domain_classifier": self.domain_classifier_dim1,
                "task_classifier": self.task_classifier_dim1,
                "criterion": self.criterion,
                "feature_optimizer": self.feature_optimizer_dim1,
                "domain_optimizer": self.domain_optimizer_dim1,
                "task_optimizer": self.task_optimizer_dim1,
            }
            config = {
                "num_epochs": self.num_epochs_dim1,
                "is_target_weights": self.is_target_weights,
                "device": self.device,
                "do_early_stop": self.do_early_stop,
            }
        elif FLAGS.algo_name == "CoRAL":
            network = {
                "feature_extractor": self.feature_extractor,
                "task_classifier": self.task_classifier_dim1,
                "criterion": self.criterion,
                "feature_optimizer": self.feature_optimizer_dim1,
                "task_optimizer": self.task_optimizer_dim1,
            }
            config = {
                "num_epochs": self.num_epochs_dim1,
                "device": self.device,
                "do_early_stop": self.do_early_stop,
            }
        elif FLAGS.algo_name == "JDOT":
            network = {
                "feature_extractor": self.feature_extractor,
                "task_classifier": self.task_classifier_dim1,
                "criterion": self.criterion,
                "feature_optimizer": self.feature_optimizer_dim1,
                "task_optimizer": self.task_optimizer_dim1,
            }
            config = {
                "num_epochs": self.num_epochs_dim1,
                "device": self.device,
                "do_early_stop": self.do_early_stop,
            }
        self.feature_extractor, self.task_classifier_dim1, _ = ALGORYTHMS[FLAGS.algo_name].fit(data, network, **config)

    def fit_2nd_dim(
        self,
        source_ds: torch.utils.data.TensorDataset,
        target_ds: torch.utils.data.TensorDataset,
        test_target_X: torch.Tensor,
        test_target_y_task: torch.Tensor,
    ):
        if FLAGS.is_RV_tuning:
            return self._fit_RV_2nd_dim(source_ds, target_ds, test_target_X, test_target_y_task)
        else:
            source_loader = DataLoader(source_ds, batch_size=self.batch_size, shuffle=True)
            target_loader = DataLoader(target_ds, batch_size=self.batch_size, shuffle=True)
            self._fit_2nd_dim(source_loader, target_loader, test_target_X, test_target_y_task)
            self.set_eval()
            pred_y_task = self.predict(test_target_X, is_1st_dim=False)
            acc = sum(pred_y_task == test_target_y_task) / len(pred_y_task)
            return acc.item()

    def _fit_RV_2nd_dim(
        self,
        source_ds: torch.utils.data.TensorDataset,
        target_ds: torch.utils.data.TensorDataset,
        test_target_X: torch.Tensor,
        test_target_y_task: torch.Tensor,
    ) -> float:
        # 1. split source into train, val
        train_source_loader, val_source_loader = utils.tensordataset_to_splitted_loaders(source_ds, self.batch_size)
        train_target_loader, val_target_loader = utils.tensordataset_to_splitted_loaders(target_ds, self.batch_size)

        # 2. free params
        free_params = [
            {"lr": 0.00001, "eps": 1e-08, "weight_decay": 0},
            {"lr": 0.0001, "eps": 1e-08, "weight_decay": 0},
            {"lr": 0.001, "eps": 1e-08, "weight_decay": 0},
        ]
        RV_scores = {"free_params": [], "scores": []}
        tmp = self.feature_extractor

        for param in free_params:
            self.__init__(self.experiment)
            self.feature_extractor.load_state_dict(tmp.state_dict())
            self.feature_optimizer_dim2.param_groups[0].update(param)
            self.domain_optimizer_dim2.param_groups[0].update(param)
            self.task_optimizer_dim2.param_groups[0].update(param)

            # 3. RV algo
            ## 3.1 fit f_i
            val_source_X = torch.cat([X for X, _ in val_source_loader], dim=0)
            if self.task_classifier_dim1.output_size == 1:
                val_source_y_task = torch.cat([y[:, utils.COL_IDX_TASK] > 0.5 for _, y in val_source_loader], dim=0)
            else:
                val_source_y_task = torch.cat([y[:, :-1].argmax(dim=1) for _, y in val_source_loader], dim=0)
            self.do_early_stop = True
            self._fit_2nd_dim(train_source_loader, train_target_loader, val_source_X, val_source_y_task)
            ## 3.2 fit \bar{f}_i
            train_target_X = torch.cat([X for X, _ in train_target_loader], dim=0)
            train_target_pred_y_task = self.predict(train_target_X, is_1st_dim=False)
            val_target_X = torch.cat([X for X, _ in val_target_loader], dim=0)
            val_target_pred_y_task = self.predict(val_target_X, is_1st_dim=False)

            train_target_ds = TensorDataset(
                train_target_X,
                torch.cat(
                    [
                        train_target_pred_y_task.reshape(-1, 1),
                        torch.zeros_like(train_target_pred_y_task).reshape(-1, 1).to(torch.float32),
                    ],
                    dim=1,
                ),
            )
            target_as_source_loader = DataLoader(train_target_ds, batch_size=self.batch_size, shuffle=True)

            train_source_X = torch.cat([X for X, _ in train_source_loader], dim=0)
            train_source_ds = TensorDataset(
                train_source_X, torch.ones(train_source_X.shape[0]).to(torch.float32).to(self.device)
            )
            train_source_as_target_loader = DataLoader(train_source_ds, batch_size=self.batch_size, shuffle=True)

            self.__init__(self.experiment)
            self.feature_extractor.load_state_dict(tmp.state_dict())
            self.feature_optimizer_dim1.param_groups[0].update(param)
            self.domain_optimizer_dim1.param_groups[0].update(param)
            self.task_optimizer_dim1.param_groups[0].update(param)
            self.do_early_stop = True
            self._fit_1st_dim(
                target_as_source_loader, train_source_as_target_loader, val_target_X, val_target_pred_y_task
            )
            ## 3.3 get RV loss
            pred_y_task = self.predict(val_source_X, is_1st_dim=True)
            acc_RV = sum(pred_y_task == val_source_y_task) / val_source_y_task.shape[0]
            RV_scores["free_params"].append(param)
            RV_scores["scores"].append(acc_RV.item())
        # 4. Retraining
        best_param = RV_scores["free_params"][np.argmax(RV_scores["scores"])]

        self.__init__(self.experiment)
        self.feature_extractor.load_state_dict(tmp.state_dict())
        # self.feature_optimizer_dim2 = optim.Adam(self.feature_extractor.parameters())
        # TODO: Understand that this line causes lower evaluation score

        self.feature_optimizer_dim2.param_groups[0].update(best_param)
        self.domain_optimizer_dim2.param_groups[0].update(best_param)
        self.task_optimizer_dim2.param_groups[0].update(best_param)
        source_loader = DataLoader(source_ds, batch_size=self.batch_size, shuffle=True)
        target_loader = DataLoader(target_ds, batch_size=self.batch_size, shuffle=True)
        if self.experiment == "MNIST":
            self.do_early_stop = True
        else:
            self.do_early_stop = False
        self._fit_2nd_dim(source_loader, target_loader, val_source_X, val_source_y_task)
        self.set_eval()
        pred_y_task = self.predict(test_target_X, is_1st_dim=False)
        acc = sum(pred_y_task == test_target_y_task) / test_target_y_task.shape[0]
        return acc.item()

    def _fit_2nd_dim(self, source_loader, target_loader, test_target_X: torch.Tensor, test_target_y_task: torch.Tensor):
        data = {
            "source_loader": source_loader,
            "target_loader": target_loader,
            "target_X": test_target_X,
            "target_y_task": test_target_y_task,
        }
        if FLAGS.algo_name == "DANN":
            network = {
                "feature_extractor": self.feature_extractor,
                "domain_classifier": self.domain_classifier_dim2,
                "task_classifier": self.task_classifier_dim2,
                "criterion": self.criterion,
                "feature_optimizer": self.feature_optimizer_dim2,
                "domain_optimizer": self.domain_optimizer_dim2,
                "task_optimizer": self.task_optimizer_dim2,
            }
            config = {
                "num_epochs": self.num_epochs_dim2,
                "is_psuedo_weights": True,
                "is_target_weights": self.is_target_weights,
                "device": self.device,
                "do_early_stop": self.do_early_stop,
            }
        elif FLAGS.algo_name == "CoRAL":
            network = {
                "feature_extractor": self.feature_extractor,
                "task_classifier": self.task_classifier_dim2,
                "criterion": self.criterion,
                "feature_optimizer": self.feature_optimizer_dim2,
                "task_optimizer": self.task_optimizer_dim2,
            }
            config = {
                "num_epochs": self.num_epochs_dim2,
                "is_psuedo_weights": True,
                "device": self.device,
                "do_early_stop": self.do_early_stop,
            }
        elif FLAGS.algo_name == "JDOT":
            network = {
                "feature_extractor": self.feature_extractor,
                "task_classifier": self.task_classifier_dim2,
                "criterion": self.criterion,
                "feature_optimizer": self.feature_optimizer_dim2,
                "task_optimizer": self.task_optimizer_dim2,
            }
            config = {
                "num_epochs": self.num_epochs_dim2,
                "is_psuedo_weights": True,
                "device": self.device,
                "do_early_stop": self.do_early_stop,
            }
        self.feature_extractor, self.task_classifier_dim2, _ = ALGORYTHMS[FLAGS.algo_name].fit(data, network, **config)

    def predict(self, X: torch.Tensor, is_1st_dim: bool) -> torch.Tensor:
        if is_1st_dim:
            return self.task_classifier_dim1.predict(self.feature_extractor(X))
        else:
            return self.task_classifier_dim2.predict(self.feature_extractor(X))

    def predict_proba(self, X: torch.Tensor, is_1st_dim: bool) -> torch.Tensor:
        if is_1st_dim:
            return self.task_classifier_dim1.predict_proba(self.feature_extractor(X))
        else:
            return self.task_classifier_dim2.predict_proba(self.feature_extractor(X))

    def set_eval(self):
        self.task_classifier_dim2.eval()
        self.feature_extractor.eval()
