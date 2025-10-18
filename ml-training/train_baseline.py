import torch
from tqdm import tqdm
import editdistance
import matplotlib.pyplot as plt
import time

def train(model, optimizer, criterion, iterator, device, labels_to_text, idx2p):
    model.train()
    epoch_loss = 0
    for (src, trg) in tqdm(iterator):
        src, trg = src.to(device), trg.to(device)
        optimizer.zero_grad()
        output = model(src, trg[:-1, :])
        loss = criterion(output.view(-1, output.shape[-1]), trg[1:, :].reshape(-1))
        loss.backward()
        optimizer.step()
        epoch_loss += loss.item()
    return epoch_loss / len(iterator)

def evaluate(model, criterion, iterator, device):
    model.eval()
    epoch_loss = 0
    with torch.no_grad():
        for (src, trg) in tqdm(iterator):
            src, trg = src.to(device), trg.to(device)
            output = model(src, trg[:-1, :])
            loss = criterion(output.view(-1, output.shape[-1]), trg[1:, :].reshape(-1))
            epoch_loss += loss.item()
    return epoch_loss / len(iterator)

def validate(model, dataloader, device, show=10, editdistance=None, labels_to_text=None, idx2p=None, p2idx=None):
    model.eval()
    show_count = 0
    error_p = 0
    len_p = 0
    word_eds, word_true_lens = [], []
    with torch.no_grad():
        for (src, trg) in dataloader:
            src, trg = src.to(device), trg.to(device)

            # --- BEGIN feature extraction, must match model.forward() ---
            x = model.backbone.conv1(src)
            x = model.backbone.bn1(x)
            x = model.backbone.relu(x)
            x = model.backbone.maxpool(x)
            x = model.backbone.layer1(x)
            x = model.backbone.layer2(x)
            x = model.backbone.layer3(x)
            x = model.backbone.layer4(x)
            x = model.backbone.fc(x)  # (batch, hidden, H, W)
            b, c, h, w = x.shape
            x = x.permute(0, 2, 3, 1).reshape(b, h * w, c)  # (batch, seq_len, hidden)
            x = x.permute(1, 0, 2)  # (seq_len, batch, hidden)
            # --- END feature extraction ---

            memory = model.transformer.encoder(model.pos_encoder(x))
            out_indexes = [p2idx['SOS']]
            for _ in range(100):
                trg_tensor = torch.LongTensor(out_indexes).unsqueeze(1).to(device)
                output = model.fc_out(model.transformer.decoder(
                    model.pos_decoder(model.decoder(trg_tensor)), memory))
                out_token = output.argmax(2)[-1].item()
                out_indexes.append(out_token)
                if out_token == p2idx['EOS']:
                    break
            out_p = labels_to_text(out_indexes[1:], idx2p)
            real_p = labels_to_text(trg[1:, 0].cpu().numpy(), idx2p)
            distance = editdistance.eval(out_p, real_p) if out_p else len(real_p)
            error_p += distance
            len_p += len(real_p)
            pred_words = out_p.split()
            true_words = real_p.split()
            word_eds.append(editdistance.eval(pred_words, true_words))
            word_true_lens.append(len(true_words))
            if show > show_count:
                print('Real:', real_p)
                print('Pred:', out_p)
                print(distance / len(real_p) * 100 if len(real_p) > 0 else None)
                show_count += 1
    # Avoid division by zero
    len_p = max(len_p, 1)
    sum_word_true = max(sum(word_true_lens), 1)
    return error_p / len_p * 100, sum(word_eds) / sum_word_true * 100

def train_baseline_model(
    model,
    optimizer,
    criterion,
    train_loader,
    val_loader,
    scheduler,
    best_eval_loss_cer,
    device,
    epochs,
    valid_loss_all,
    train_loss_all,
    eval_loss_cer_all,
    eval_accuracy_all,
    labels_to_text,
    idx2p,
    p2idx,
    checkpoint_dir,
    max_epochs=1000,
):
    print(f"Training on device: {device}")
    count_bad = 0
    for epoch in range(epochs, max_epochs):
        print(f'Epoch: {epoch + 1:02}')
        start_time = time.time()

        # Training Loop
        print("-----------train------------")
        train_loss = train(model, optimizer, criterion, train_loader, device, labels_to_text, idx2p)
        print("-----------valid------------")
        valid_loss = evaluate(model, criterion, val_loader, device)
        print("-----------eval------------")
        eval_loss_cer, eval_accuracy = validate(model, val_loader, device, show=10,  editdistance=editdistance, labels_to_text=labels_to_text, idx2p=idx2p, p2idx=p2idx)
        scheduler.step(eval_loss_cer)
        valid_loss_all.append(valid_loss)
        train_loss_all.append(train_loss)
        eval_loss_cer_all.append(eval_loss_cer)
        eval_accuracy_all.append(eval_accuracy)

        # Robust model saving (works with or without DataParallel)
        model_state = getattr(model, 'module', model).state_dict()
        checkpoint = {
            'model': model_state,
            'epoch': epoch,
            'best_eval_loss_cer': best_eval_loss_cer,
            'valid_loss_all': valid_loss_all,
            'train_loss_all': train_loss_all,
            'eval_loss_cer_all': eval_loss_cer_all,
            'eval_accuracy_all': eval_accuracy_all,
        }

        if eval_loss_cer < best_eval_loss_cer:
            count_bad = 0
            best_eval_loss_cer = eval_loss_cer
            torch.save(checkpoint, f'{checkpoint_dir}/resnet50_trans_{best_eval_loss_cer:.3f}.pt')
            print('Save best model')
        else:
            count_bad += 1
            torch.save(checkpoint, f'{checkpoint_dir}/resnet50_trans_last.pt')
            print('Save model')

        print(f'Time: {time.time() - start_time:.1f}s')
        print(f'Train Loss: {train_loss:.4f}')
        print(f'Val   Loss: {valid_loss:.4f}')
        print(f'Eval  CER: {eval_loss_cer:.4f}')
        print(f'Eval accuracy: {eval_accuracy:.4f}')

        # Plotting (only last 20 points for clarity)
        plt.clf()
        plt.plot(valid_loss_all[-20:], label="Valid Loss")
        plt.plot(train_loss_all[-20:], label="Train Loss")
        plt.legend()
        plt.savefig(f'{checkpoint_dir}/all_loss.png')
        plt.clf()
        plt.plot(eval_loss_cer_all[-20:])
        plt.savefig(f'{checkpoint_dir}/loss_cer.png')
        plt.clf()
        plt.plot(eval_accuracy_all[-20:])
        plt.savefig(f'{checkpoint_dir}/eval_accuracy.png')

        if count_bad > 19:
            print("Early stopping triggered.")
            break