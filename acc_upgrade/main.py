import param
from train import pretrain, adapt, evaluate,evaluate2
from model import (BertEncoder, DistilBertEncoder, DistilKobertEncoder,
                   BertClassifier, Discriminator, KobertEncoder)
from utils import CSV2Array, convert_examples_to_features, get_data_loader, init_model
from sklearn.model_selection import train_test_split
from transformers import BertTokenizer
from tokenization_kobert import KoBertTokenizer
import torch
import os
import random
import argparse


def parse_arguments():
    # argument parsing
    parser = argparse.ArgumentParser(description="Specify Params for Experimental Setting")

    parser.add_argument('--src', type=str, default="community",
                        choices=["community","news"],
                        help="Specify src dataset")

    parser.add_argument('--tgt', type=str, default="news",
                        choices=["community","news"],
                        help="Specify tgt dataset")

    parser.add_argument('--pretrain', default=False, action='store_true',
                        help='Force to pretrain source encoder/classifier')

    parser.add_argument('--adapt', default=False, action='store_true',
                        help='Force to adapt target encoder')

    parser.add_argument('--seed', type=int, default=42,
                        help="Specify random state")

    parser.add_argument('--train_seed', type=int, default=42,
                        help="Specify random state")

    parser.add_argument('--load', default=False, action='store_true',
                        help="Load saved model")

    parser.add_argument('--model', type=str, default="kobert",
                        choices=["bert", "distilbert", "kobert", "distilkobert"],
                        help="Specify model type")

    parser.add_argument('--max_seq_length', type=int, default=128,
                        help="Specify maximum sequence length")

    parser.add_argument('--alpha', type=float, default=1.0,
                        help="Specify adversarial weight")

    parser.add_argument('--beta', type=float, default=1.0,
                        help="Specify KD loss weight")

    parser.add_argument('--temperature', type=int, default=20,
                        help="Specify temperature")

    parser.add_argument("--max_grad_norm", default=1.0, type=float,
                        help="Max gradient norm.")

    parser.add_argument("--clip_value", type=float, default=0.01,
                        help="lower and upper clip value for disc. weights")

    parser.add_argument('--batch_size', type=int, default=32,
                        help="Specify batch size")

    parser.add_argument('--pre_epochs', type=int, default=3,
                        help="Specify the number of epochs for pretrain")

    parser.add_argument('--pre_log_step', type=int, default=1,
                        help="Specify log step size for pretrain")

    parser.add_argument('--num_epochs', type=int, default=3,
                        help="Specify the number of epochs for adaptation")

    parser.add_argument('--log_step', type=int, default=1,
                        help="Specify log step size for adaptation")

    return parser.parse_args()


def set_seed(seed):
    random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.device_count() > 0:
        torch.cuda.manual_seed_all(seed)


def main():
    args = parse_arguments()
    # argument setting
    print("=== Argument Setting ===")
    print("src: " + args.src)
    print("tgt: " + args.tgt)
    print("seed: " + str(args.seed))
    print("train_seed: " + str(args.train_seed))
    print("model_type: " + str(args.model))
    print("max_seq_length: " + str(args.max_seq_length))
    print("batch_size: " + str(args.batch_size))
    print("pre_epochs: " + str(args.pre_epochs))
    print("num_epochs: " + str(args.num_epochs))
    print("AD weight: " + str(args.alpha))
    print("KD weight: " + str(args.beta))
    print("temperature: " + str(args.temperature))
    set_seed(args.train_seed)

    if args.model in ['kobert', 'distilkobert']:
        tokenizer = BertTokenizer.from_pretrained('monologg/kobert')
    else:
        tokenizer = BertTokenizer.from_pretrained('bert-base-multilingual-cased')

    # preprocess data
    print("=== Processing datasets ===")
    if args.src in ['community','news']:
        src_x, src_y = CSV2Array(os.path.join('/content/bert-AAD/data', args.src, args.src + '.csv'))

    src_x, src_test_x, src_y, src_test_y = train_test_split(src_x, src_y,
                                                            test_size=0.1,
                                                            stratify=src_y,
                                                            random_state=args.seed)

    if args.tgt in ['community','news']:
        tgt_x, tgt_y = CSV2Array(os.path.join('/content/bert-AAD/data', args.tgt, args.tgt + '.csv'))

    tgt_train_x, tgt_test_y, tgt_train_y, tgt_test_y = train_test_split(tgt_x, tgt_y,
                                                                        test_size=0.1,
                                                                        stratify=tgt_y,
                                                                        random_state=args.seed)

    src_features = convert_examples_to_features(src_x, src_y, args.max_seq_length, tokenizer)
    src_test_features = convert_examples_to_features(src_test_x, src_test_y, args.max_seq_length, tokenizer)
    tgt_features = convert_examples_to_features(tgt_x, tgt_y, args.max_seq_length, tokenizer)
    tgt_train_features = convert_examples_to_features(tgt_train_x, tgt_train_y, args.max_seq_length, tokenizer)

    # load dataset

    src_data_loader = get_data_loader(src_features, args.batch_size)
    src_data_eval_loader = get_data_loader(src_test_features, args.batch_size)
    tgt_data_train_loader = get_data_loader(tgt_train_features, args.batch_size)
    tgt_data_all_loader = get_data_loader(tgt_features, args.batch_size)

    # load models
    if args.model == 'bert':
        src_encoder = BertEncoder()
        tgt_encoder = BertEncoder()
        src_classifier = BertClassifier()
    elif args.model == 'distilbert':
        src_encoder = DistilBertEncoder()
        tgt_encoder = DistilBertEncoder()
        src_classifier = BertClassifier()
    elif args.model == 'kobert':
        src_encoder = KobertEncoder()
        tgt_encoder = KobertEncoder()
        src_classifier = BertClassifier()
    else:
        src_encoder = DistilKobertEncoder()
        tgt_encoder = DistilKobertEncoder()
        src_classifier = BertClassifier()
    discriminator = Discriminator()

    if args.load:
        src_encoder = init_model(args, src_encoder, restore=param.src_encoder_path)
        src_classifier = init_model(args, src_classifier, restore=param.src_classifier_path)
        tgt_encoder = init_model(args, tgt_encoder, restore=param.tgt_encoder_path)
        discriminator = init_model(args, discriminator, restore=param.d_model_path)
    else:
        src_encoder = init_model(args, src_encoder)
        src_classifier = init_model(args, src_classifier)
        tgt_encoder = init_model(args, tgt_encoder)
        discriminator = init_model(args, discriminator)
    # train source model
    print("SOURCE DOMIAN SET으로 학습 시작")
    if args.pretrain:
        src_encoder, src_classifier = pretrain(
            args, src_encoder, src_classifier, src_data_loader)

    # eval source model
    print("SOURCE DOMAIN SET에 대해서 학습을 수행한 모델을 SOURCE DOMIAN의 TRAIN SET으로 검증한 결과")
    evaluate(src_encoder, src_classifier, src_data_loader)
    print("SOURCE DOMAIN SET에 대해서 학습을 수행한 모델을 SOURCE DOMIAN의 TEST SET으로 검증한 결과")
    evaluate(src_encoder, src_classifier, src_data_eval_loader)
    print("SOURCE DOMAIN SET에 대해서 학습을 수행한 모델을 TARGET DOMIAN의 TEST SET으로 검증한 결과")
    evaluate(src_encoder, src_classifier, tgt_data_all_loader)

    for params in src_encoder.parameters():
        params.requires_grad = False

    for params in src_classifier.parameters():
        params.requires_grad = False

    # train target encoder by GAN
    print("=== Training encoder for target domain ===")
    if args.adapt:
        tgt_encoder.load_state_dict(src_encoder.state_dict())
        tgt_encoder = adapt(args, src_encoder, tgt_encoder, discriminator,
                            src_classifier, src_data_loader, tgt_data_train_loader, tgt_data_all_loader)

    # eval target encoder on lambda0.1 set of target dataset
    print("DA 적용 전 결과")
    evaluate(src_encoder, src_classifier, tgt_data_all_loader)
    print("DA 적용 후 결과")
    evaluate2(tgt_encoder, src_classifier, tgt_data_all_loader)


if __name__ == '__main__':
    main()
