class Hparams:
    def __init__(self):
        self.checkpoint_dir = './'
        self.trans_dir = './data/texts'
        self.image_dir = './data/images'
        self.test_dir = '/data/'
        self.del_sym = ['b', 'd', 'a', 'c', '×', '⊕', '|', 'n', 'm', 'g', 'ǂ', 'k', 'o', '–', '⊗', 'l', '…', 'u','h', 'f','t','p', 'r', 'e','s', 'Θ', 'Ψ', 'θ', 'H', 'N', 'J', 'S', 'T', 'V', 'Z', '_', '`', 'v', 'y', 'z', '}', "[", "]", "\t", "є", '√', "B", "D", "F", "G", "L", "M", "R", "U", "W", "j", "w", "~", ]
        self.lr = 1e-4
        self.batch_size = 32
        self.hidden = 512
        self.enc_layers = 1
        self.dec_layers = 1
        self.nhead = 4
        self.dropout = 0.1
        self.width = 1024
        self.height = 128