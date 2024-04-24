from typing import List

import matplotlib.pyplot as plt
import numpy as np
import torch
from sklearn.datasets import make_moons
from sklearn.manifold import TSNE
from torch.utils.data import DataLoader, TensorDataset

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")
COL_IDX_TASK = 0
COL_IDX_DOMAIN = 1


def get_source_target_from_make_moons(n_samples=100, noise=0.05, rotation_degree=-30):
    # pylint: disable=too-many-locals
    # It seems reasonable in this case, since this method needs all of that.
    """
    Get source and target data in domain adaptation problem,
    generated by sklean.datasets.make_moons.

    Parameters
    ----------
    n_samples : int
        Represents the number of make_moons samples to be generated.

    noise : int
        Represents standard deviation of gaussian noise.

    rotatin_degree : int
        Represents degree to be rotated.
        Used for generating unsupervised target data in domain adaptation problem.

    Returns
    -------
    source_X : ndarray of shape(n_samples, 2)
        The generated source feature.

    target_X : ndarray of shape(n_samples, 2)
        The generated target feature.

    source_y : ndarray of shape(n_samples, )
        The generated source label.

    target_y : ndarray of shape(n_samples, )
        The generated target label, this is not used for ML model training.

    x_grid : ndarray of shape(2, 10000)
        Stacked meshgrid points, each row is each dimension, used for visualization.

    x1_grid : ndarray of shape(100, 100)
        The first dimentional Meshgrid points, used for visualization.

    x2_grid : ndarray of shape(100, 100)
        The second dimentional Meshgrid points, used for visualization.
    """
    source_X, source_y = make_moons(n_samples=n_samples, noise=noise)
    source_X[:, 0] -= 0.5
    theta = np.radians(rotation_degree)
    cos, sin = np.cos(theta), np.sin(theta)
    rotate_matrix = np.array([[cos, -sin], [sin, cos]])
    target_X = source_X.dot(rotate_matrix)
    target_y = source_y

    x1_min, x2_min = np.min([source_X.min(0), target_X.min(0)], axis=0)
    x1_max, x2_max = np.max([source_X.max(0), target_X.max(0)], axis=0)
    x1_grid, x2_grid = np.meshgrid(
        np.linspace(x1_min - 0.1, x1_max + 0.1, 100), np.linspace(x2_min - 0.1, x2_max + 0.1, 100)
    )
    x_grid = np.stack([x1_grid.reshape(-1), x2_grid.reshape(-1)], axis=0)
    return source_X, target_X, source_y, target_y, x_grid, x1_grid, x2_grid


def get_loader(
    source_X: np.ndarray,
    target_X: np.ndarray,
    source_y_task: np.ndarray,
    target_y_task: np.ndarray,
    batch_size: int = 34,
    shuffle: bool = False,
    output_size: int = 1
):
    """
    Get instances of torch.utils.data.DataLoader for domain invariant learning,
    also return source and target data instantiated as torch.Tensor.

    Parameters
    ----------
    source_X : ndarray of shape(N, D) or (N, T, D)
    target_X : ndarray of shape(N, D) or (N, T, D)
    source_y_task : ndarray of shape(N, )
    target_y_task : ndarray of shape(N, )
    batch_size : int
    shuffle : boolean

    Returns
    -------
    source_loader : torch.utils.data.dataloader.DataLoader
        Contains source's feature, task label and domain label.
    target_loader : torch.utils.data.dataloader.DataLoader
        Contains target's feature, domain label.

    source_X : torch.Tensor of shape(N, D) or (N, T, D)
    source_y_task : ndarray of shape(N, 1)
    target_X : torch.Tensor of shape(N, D) or (N, T, D)
    target_y_task : torch.Tensor of shape(N, )
    """
    # 1. Create y_domain
    if source_y_task.ndim > 1:
        source_y_domain = np.zeros(source_y_task.shape[0]).reshape(-1, 1)
    else:
        source_y_domain = np.zeros_like(source_y_task).reshape(-1, 1)
    if output_size == 1:
        source_y_task = source_y_task.reshape(-1, 1)
    source_Y = np.concatenate([source_y_task, source_y_domain], axis=1)
    target_y_domain = np.ones_like(target_y_task)

    # 2. Instantiate torch.tensor
    # TODO: E1102: torch.tensor is not callable (not-callable)
    source_X = torch.tensor(source_X, dtype=torch.float32)
    source_Y = torch.tensor(source_Y, dtype=torch.float32)
    target_X = torch.tensor(target_X, dtype=torch.float32)
    target_y_domain = torch.tensor(target_y_domain, dtype=torch.float32)
    target_y_task = torch.tensor(target_y_task, dtype=torch.float32)

    # 3. To GPU
    source_X = source_X.to(DEVICE)
    source_Y = source_Y.to(DEVICE)
    target_X = target_X.to(DEVICE)
    target_y_domain = target_y_domain.to(DEVICE)
    target_y_task = target_y_task.to(DEVICE)

    # 4. Instantiate DataLoader
    source_ds = TensorDataset(source_X, source_Y)
    target_ds = TensorDataset(target_X, target_y_domain)
    source_loader = DataLoader(source_ds, batch_size=batch_size, shuffle=shuffle)
    target_loader = DataLoader(target_ds, batch_size=batch_size, shuffle=shuffle)

    return source_loader, target_loader, source_y_task, source_X, target_X, target_y_task


def apply_sliding_window(X: np.ndarray, y: np.ndarray, filter_len: int = 3, is_overlap: bool = True) -> (np.ndarray, np.ndarray):
    """
    Parameters
    ----------
    X : ndarray of shape(N, H)
    y : ndarray of shape(N, )
    filter_len : int
    is_overlap: bool

    Returns
    -------
    filtered_X : 
        ndarray of shape(N - filter_len + 1, filter_len, H) when is_ovelap == True:
        ndarray of shape(N//filter_len, filter_len, H) when is_ovelap == False:
    filtered_y : 
        ndarray of shape(N - filter_len + 1, ) when is_ovelap == True:
        ndarray of shape(N//filter_len, ) when is_ovelap == False:
    """
    len_data, H = X.shape
    if is_overlap:
        N = len_data - filter_len + 1
        filtered_X = np.zeros((N, filter_len, H))
        for i in range(0, N):
            # print(f"(Start, End) = {i, i+filter_len-1}")
            start = i
            end = i + filter_len
            filtered_X[i] = X[start:end]
        filtered_y = y[filter_len - 1:]
        return filtered_X, filtered_y
    
    else:
        X = np.expand_dims(X, axis=1)
        i = 0
        filtered_Xs = []
        filtered_ys = []
        while i < len_data-filter_len:
            filtered_X = np.expand_dims(np.concatenate(X[i:i+filter_len], axis=0), axis=0)
            filtered_Xs.append(filtered_X)
            filtered_ys.append(y[i+filter_len-1])
            i += filter_len
        return np.vstack(filtered_Xs), np.array(filtered_ys).reshape(-1)
            

def _change_lr_during_dann_training(
    domain_optimizer: torch.optim.Adam,
    feature_optimizer: torch.optim.Adam,
    task_optimizer: torch.optim.Adam,
    epoch: torch.Tensor,
    epoch_thr: int = 200,
    lr: float = 0.00005,
):
    """
    Returns
    -------
    domain_optimizer : torch.optim.adam.Adam
    feature_optimizer : torch.optim.adam.Adam
    task_optimizer : torch.optim.adam.Adam
    """
    if epoch == epoch_thr:
        domain_optimizer.param_groups[0]["lr"] = lr
        feature_optimizer.param_groups[0]["lr"] = lr
        task_optimizer.param_groups[0]["lr"] = lr
    return domain_optimizer, feature_optimizer, task_optimizer


def _get_psuedo_label_weights(source_Y_batch: torch.Tensor, thr: float = 0.75, alpha: int = 1) -> torch.Tensor:
    """
    # TODO: attach paper

    Parameters
    ----------
    source_Y_batch : torch.Tensor of shape(N, 2)
    thr : float

    Returns
    -------
    psuedo_label_weights : torch.Tensor of shape(N, )
    """
    output_size = source_Y_batch[:, :-1].shape[1]
    psuedo_label_weights = []

    if output_size == 1:
        pred_y = source_Y_batch[:, COL_IDX_TASK]        
        for i in pred_y:
            if i > thr:
                psuedo_label_weights.append(1)
            elif i < 1 - thr:
                psuedo_label_weights.append(1)
            else:
                if i > 0.5:
                    psuedo_label_weights.append(i**alpha + (1 - thr))
                else:
                    psuedo_label_weights.append((1 - i)**alpha + (1 - thr))

    else:
        pred_y = source_Y_batch[:, :output_size]
        pred_y = torch.max(pred_y, axis=1).values
        for i in pred_y:
            if i > thr:
                psuedo_label_weights.append(1)
            else:
                psuedo_label_weights.append(i**alpha + (1 - thr))
    return torch.tensor(psuedo_label_weights, dtype=torch.float32).to(DEVICE)


def _get_terminal_weights(
    is_target_weights: bool,
    is_class_weights: bool,
    is_psuedo_weights: bool,
    pred_source_y_domain: torch.Tensor,
    source_y_task_batch: torch.Tensor,
    psuedo_label_weights: torch.Tensor,
) -> torch.Tensor:
    """
    # TODO: attach paper

    Parameters
    ----------
    is_target_weights: bool
    is_class_weights: bool
    is_psuedo_weights: bool
    pred_source_y_domain : torch.Tensor of shape(N, )
    source_y_task_batch : torch.Tensor of shape(N, )
    psuedo_label_weights : torch.Tensor of shape(N, )

    Returns
    -------
    weights : torch.Tensor of shape(N, )
    terminal sample weights for nn.BCELoss
    """
    if is_target_weights:
        target_weights = pred_source_y_domain / (1 - pred_source_y_domain)
    else:
        target_weights = 1
    if is_class_weights:
        class_weights = get_class_weights(source_y_task_batch)
    else:
        class_weights = 1
    if is_psuedo_weights:
        weights = target_weights * class_weights * psuedo_label_weights
    else:
        weights = target_weights * class_weights
    return weights


def _plot_dann_loss(
    do_plot: bool, loss_domains: List[float], loss_tasks: List[float], loss_task_evals: List[float]
) -> None:
    """
    plot domain&task losses for source, task loss for target.

    Parameters
    ----------
    do_plot: bool
    loss_domains: list of float
    loss_tasks: list of float
    loss_tasks_evals: list of float
    task loss for target data.
    """
    if do_plot:
        plt.figure()
        plt.plot(loss_domains, label="loss_domain")
        plt.plot(loss_tasks, label="loss_task")
        plt.xlabel("batch")
        plt.ylabel("cross entropy loss")
        plt.legend()

        plt.figure()
        plt.plot(loss_task_evals, label="loss_task_eval")
        plt.xlabel("epoch")
        plt.ylabel("accuracy")
        plt.legend()
        plt.show()


def fit_without_adaptation(source_loader, task_classifier, task_optimizer, criterion, num_epochs=1000):
    """
    Deep Learning model's fit method without domain adaptation.

    Parameters
    ----------
    source_loader : torch.utils.data.DataLoader
        Contains source's feature, task label and domain label.
        Domain Label is not used in this method.

    task_classifier : subclass of torch.nn.Module
        Target Deep Learning model.
        Currently it should output one dimensional prediction(only accept binary classification).

    task_optimizer : subclass of torch.optim.Optimizer
        Optimizer required instantiation with task_classifier.parameters().

    criterion : torch.nn.modules.loss.BCELoss
        Instance calculating Binary Cross Entropy Loss.

    num_epochs : int
    """
    for _ in range(num_epochs):
        for source_X_batch, source_Y_batch in source_loader:
            # Prep Data
            source_y_task_batch = source_Y_batch[:, COL_IDX_TASK]

            # Forward
            pred_y_task = task_classifier(source_X_batch)
            pred_y_task = torch.sigmoid(pred_y_task).reshape(-1)
            loss_task = criterion(pred_y_task, source_y_task_batch)

            # Backward
            task_optimizer.zero_grad()
            loss_task.backward()

            # Updata Params
            task_optimizer.step()
    return task_classifier


def visualize_tSNE(target_feature, source_feature):
    """
    Draw scatter plot including t-SNE encoded feature for source and target data.
    Small difference between them imply success of domain invarinat learning
    (only in the point of domain invariant).

    Parameters
    ----------
    target_feature : ndarray of shape(N, D)
        N is the number of samples, D is the number of features.

    source_feature : ndarray of shape(N, D)
    """
    tsne = TSNE(n_components=2, learning_rate="auto", init="pca", perplexity=5)
    # TODO: Understand Argumetns for t-SNE
    target_feature_tsne = tsne.fit_transform(target_feature)
    source_feature_tsne = tsne.fit_transform(source_feature)

    plt.figure()
    plt.scatter(source_feature_tsne[:, 0], source_feature_tsne[:, 1], label="Source")
    plt.scatter(target_feature_tsne[:, 0], target_feature_tsne[:, 1], label="Target")
    plt.xlabel("tsne_X1")
    plt.ylabel("tsne_X2")
    plt.legend()
    plt.show()


def get_class_weights(source_y_task_batch):
    p_occupied = sum(source_y_task_batch) / source_y_task_batch.shape[0]
    p_unoccupied = 1 - p_occupied
    class_weights = torch.zeros_like(source_y_task_batch)
    for i, y in enumerate(source_y_task_batch):
        if y == 1:
            class_weights[i] = p_unoccupied
        elif y == 0:
            class_weights[i] = p_occupied
    return class_weights
