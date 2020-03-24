import torch
import time
import torchvision
from torchvision import utils
import torchvision.transforms as transforms
import torch.optim as optim
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

LOGS_DIR = 'tb_logs'
BATCH_SIZE = 32
WORKERS = 4

train_on_gpu = torch.cuda.is_available()

if train_on_gpu:
    print(f"CUDA is available! Training on {torch.cuda.get_device_name(0)}...")
    device = torch.device("cuda:0")
else:
    print("CUDA is not available. Training on CPU...")
    device = 'cpu'

transform = transforms.Compose(
    [transforms.ToTensor(),
     transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])

trainset = torchvision.datasets.CIFAR10(root='./data', train=True, download=True, transform=transform)
trainloader = torch.utils.data.DataLoader(trainset, batch_size=BATCH_SIZE, shuffle=True, num_workers=WORKERS)

testset = torchvision.datasets.CIFAR10(root='./data', train=False, download=True, transform=transform)
testloader = torch.utils.data.DataLoader(testset, batch_size=BATCH_SIZE, shuffle=False, num_workers=WORKERS)

classes = ('plane', 'car', 'bird', 'cat', 'deer', 'dog', 'frog', 'horse', 'ship', 'truck')


class CNN(nn.Module):
    def __init__(self):
        super(CNN, self).__init__()
        self.pool = nn.MaxPool2d(2, 2)

        self.conv1 = nn.Conv2d(3, 16, 3, padding=1)
        self.conv2 = nn.Conv2d(16, 32, 3, padding=1)
        self.conv3 = nn.Conv2d(32, 64, 3, padding=1)
        self.flat_dim = 64 * 4 * 4
        self.batch_norm = nn.BatchNorm1d(self.flat_dim)
        self.fc1 = nn.Linear(self.flat_dim, 500)
        self.fc2 = nn.Linear(500, 10)
        self.dropout = nn.Dropout(0.25)

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))  # 32x32x3 -> 16x32x32 -> 16x16x16
        x = self.pool(F.relu(self.conv2(x)))  # 16x16x16 -> 32x16x16 -> 32x8x8
        x = self.pool(F.relu(self.conv3(x)))  # 32x8x8x -> 64x8x8 -> 64x4x4
        x = self.batch_norm(x.view(-1, self.flat_dim))  # 64x4x4 -> 1024
        x = self.dropout(x)
        x = F.relu(self.fc1(x))  # 1024 -> 500
        x = self.dropout(x)
        x = self.fc2(x)  # 500 -> 10
        return F.softmax(input=x, dim=1)


cnn = CNN()
print(cnn)


def test_data_recorder(i, pred, writer, target, data, epoch):
    global step
    labels_dict = {0: 'plane', 1: 'car', 2: 'bird', 3: 'cat', 4: 'deer', 5: 'dog', 6: 'frog',
                   7: 'horse', 8: 'ship', 9: 'truck'}

    denormalize = transforms.Normalize((-1,), (1 / 0.5,))

    # Show some misclassified images in Tensorboard
    if i < 10 and target.data[pred != target.data].nelement() > 0:
        for inx, d in enumerate(data[pred != target.data]):
            img_name = 'Test-misclassified/Prediction-{}/Label-{}_Epoch-{}_{}/'.format(
                labels_dict[pred[pred != target.data].tolist()[inx]],
                labels_dict[target.data[pred != target.data].tolist()[inx]], epoch, i)
            writer.add_image(img_name, denormalize(d), epoch)
            i += 1


def train(model, device, train_loader, opt, epoch, writer):
    model.train()

    for batch_id, (data, target) in enumerate(train_loader):
        data, target = data.to(device), target.to(device)

        # forward pass, calculate loss and backprop!
        opt.zero_grad()
        preds = model(data)
        loss = criterion(preds, target)
        loss.backward()
        opt.step()

        if batch_id % 100 == 0:
            print('Train Epoch: {} [{}/{} ({:.0f}%)]\tLoss: {:.6f}'.format(
                epoch, batch_id * len(data), len(train_loader.dataset),
                       100. * batch_id / len(train_loader), loss.item()))

    # Record training metrics
    writer.add_scalar('Train/Loss', loss.item(), epoch)
    writer.add_scalar('Train/FirstLayerAverageWeight', model.conv1.weight.mean(), epoch)
    writer.add_histogram('Train/LastLayerWeightsHistogram', model.fc2.weight.histc(bins=10), epoch)
    writer.flush()


def test(model, device, test_loader, epoch, writer):
    model.eval()  # SWITCH TO TEST MODE
    i, test_loss, correct, n = [0, 0, 0, 0]
    with torch.no_grad():
        for data, target in test_loader:
            data, target = data.to(device), target.to(device)
            output = model(data)
            test_loss += criterion(output, target).item()
            pred = output.data.max(1)[1]  # get the index of the max log-probability
            correct += pred.eq(target.data).cpu().sum()

            # Record images and data into the writer:
            test_data_recorder(i, pred, writer, target, data, epoch)

    test_loss /= len(test_loader)  # loss function already averages over batch size
    accuracy = 100. * correct / len(test_loader.dataset)
    print('\nTest set: Average loss: {:.4f}, Accuracy: {}/{} ({:.0f}%)\n'.format(
        test_loss, correct, len(test_loader.dataset),
        accuracy))

    # Record Metrics
    writer.add_scalar('Test/Loss', test_loss, epoch)
    writer.add_scalar('Test/Accuracy', accuracy, epoch)
    writer.flush()


if __name__ == '__main__':
    from torch.utils.tensorboard import SummaryWriter

    time_str = time.strftime("%Y%m%d_%H%M%S")
    writer = SummaryWriter(f"{LOGS_DIR}/{time_str}")
    print(f"'Tensorboard is recording into folder: {LOGS_DIR}/{time_str}")
    data_iter = iter(trainloader)
    images, labels = data_iter.next()

    grid = utils.make_grid(images)
    writer.add_image('Dataset/Inspect input grid', grid, 0)
    writer.close()

    step = 0

    optimizer = optim.Adam(cnn.parameters(), lr=0.0005)
    criterion = nn.CrossEntropyLoss()

    for epoch in range(0, 30):
        print("Epoch %d" % epoch)

        train(cnn, device, trainloader, optimizer, epoch, writer)
        test(cnn, device, testloader, epoch, writer)
        writer.close()
    print(f"Tensorboard is recording into folder: {LOGS_DIR}/{time_str}")
