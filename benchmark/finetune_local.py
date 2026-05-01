#!/usr/bin/env python3
"""Local LoRA fine-tune of Qwen2.5-Coder-7B on Sigil's training_corpus.jsonl.

Targets a 16GB AMD GPU via BF16 + LoRA (no 4-bit quant — bitsandbytes-rocm
is flaky). Fits with batch=1, grad_accum=8, effective batch=8.

Output: peft adapter (safetensors) at benchmark/lora_out/.
Convert to GGUF afterward with llama.cpp's convert-lora-to-gguf.py for
ollama integration.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

import torch
from datasets import Dataset
from peft import LoraConfig, get_peft_model, TaskType, prepare_model_for_kbit_training
from transformers import (
    AutoModelForCausalLM, AutoTokenizer,
    BitsAndBytesConfig,
    TrainingArguments, Trainer,
    DataCollatorForLanguageModeling,
)

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "benchmark" / "training_corpus.jsonl"
OUT = REPO / "benchmark" / "lora_out"


def load_corpus(path: Path) -> list[dict]:
    rows = []
    with path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def format_chat(example: dict, tokenizer) -> dict:
    """Convert a {messages: [...]} record to a flat token sequence using
    the tokenizer's chat template."""
    text = tokenizer.apply_chat_template(
        example["messages"],
        tokenize=False,
        add_generation_prompt=False,
    )
    return {"text": text}


def main():
    # Stable QLoRA recipe for Qwen2.5-Coder-7B on RX 7800 XT (Navi31, bf16
    # + 4-bit nf4). v2 trained successfully at lr=1e-4 / max_seq=2048; v3
    # NaN'd at the same lr after the corpus grew with longer Python refs.
    # The v3-stable knobs are encoded as defaults below — bf16+QLoRA is
    # sensitive on Navi31 to the combination of (a) long sequences amplifying
    # bf16 precision loss in the forward pass and (b) an LR ramp that pushes
    # the unstable batch over the edge during warmup. The fix that survived
    # the warmup spike at step 60: lr=2e-5, max_seq=1024, warmup_ratio=0.2.
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen2.5-Coder-7B-Instruct")
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--epochs", type=int, default=3)
    ap.add_argument("--lr", type=float, default=2e-5,
                    help="Default lowered from 1e-4 to 2e-5 after v3 NaN'd "
                         "around step 60 with long Python refs in the corpus.")
    ap.add_argument("--lora-r", type=int, default=16)
    ap.add_argument("--lora-alpha", type=int, default=32)
    ap.add_argument("--max-seq", type=int, default=1024,
                    help="Default lowered from 2048 to 1024. The 7B Qwen base "
                         "+ bf16 forward pass loses precision on long packs; "
                         "median corpus example is ~232 tokens, so this only "
                         "truncates the tail (~1% of examples).")
    ap.add_argument("--micro-batch", type=int, default=1)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--four-bit", action="store_true",
                    help="Load base in 4-bit NF4 quantization (QLoRA). "
                         "Required for 7B+ on 16GB VRAM. Bitsandbytes-rocm "
                         "smoke-tested OK on RX 7800 XT with HSA_OVERRIDE.")
    ap.add_argument("--max-grad-norm", type=float, default=1.0,
                    help="Gradient-norm clip threshold. Lower (0.3-0.5) does "
                         "NOT help once a bf16 forward overflow has produced "
                         "an inf — clip(inf)=nan still propagates. The right "
                         "fix is to keep precision in the forward pass: lower "
                         "max_seq + lower LR.")
    ap.add_argument("--warmup-ratio", type=float, default=0.2,
                    help="Default raised from 0.1 to 0.2. Longer warmup keeps "
                         "early-step LR low enough that the first hard batch "
                         "lands while the model is still in a stable region.")
    args = ap.parse_args()

    print(f"Loading tokenizer/model: {args.model}")
    tok = AutoTokenizer.from_pretrained(args.model, trust_remote_code=True)
    if tok.pad_token is None:
        tok.pad_token = tok.eos_token

    # On Navi31 (RX 7800 XT):
    #   - Full LoRA + fp16/eager: stable
    #   - QLoRA + fp16: produces NaN gradients at step 1 (bnb 4-bit + fp16 path
    #     has a known interaction issue). Use bf16 compute dtype for QLoRA;
    #     bf16 is fine here because the quantized base attenuates the
    #     instability that bf16+SDPA would have on a full-precision model.
    if args.four_bit:
        dtype = torch.bfloat16
        quantization_config = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_compute_dtype=dtype,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
        )
    else:
        dtype = torch.float16
        quantization_config = None
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=dtype,
        device_map="auto",
        trust_remote_code=True,
        attn_implementation="eager",
        quantization_config=quantization_config,
    )
    if args.four_bit:
        model = prepare_model_for_kbit_training(model)
    model.gradient_checkpointing_enable()
    if hasattr(model, "enable_input_require_grads"):
        model.enable_input_require_grads()

    # Auto-pick LoRA target modules based on the base model's actual linear
    # module names. Qwen/Llama/Mistral expose split projections (q_proj,
    # k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj). Phi-3/Phi-4
    # use fused projections (qkv_proj, gate_up_proj). Probing the model
    # avoids a silent mismatch where peft would fall through to a non-LoRA
    # forward pass.
    qwen_targets = ["q_proj", "k_proj", "v_proj", "o_proj",
                    "gate_proj", "up_proj", "down_proj"]
    phi_targets = ["qkv_proj", "o_proj", "gate_up_proj", "down_proj"]
    available_modules = {n.split(".")[-1] for n, _ in model.named_modules()}
    if "qkv_proj" in available_modules:
        target_modules = phi_targets
    elif "q_proj" in available_modules:
        target_modules = qwen_targets
    else:
        raise RuntimeError(
            f"Could not detect LoRA target modules for {args.model}. "
            f"Available leaf names: {sorted(available_modules)[:20]}")
    print(f"LoRA target modules: {target_modules}")

    lora_cfg = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        target_modules=target_modules,
        lora_dropout=0.05,
        bias="none",
        task_type=TaskType.CAUSAL_LM,
    )
    model = get_peft_model(model, lora_cfg)
    model.print_trainable_parameters()

    print(f"Loading corpus: {CORPUS}")
    rows = load_corpus(CORPUS)
    print(f"  {len(rows)} examples")
    ds = Dataset.from_list(rows)
    ds = ds.map(lambda ex: format_chat(ex, tok), remove_columns=["messages"])

    def tokenize(ex):
        out = tok(
            ex["text"],
            max_length=args.max_seq,
            truncation=True,
            padding=False,
        )
        return out
    ds = ds.map(tokenize, remove_columns=["text"])

    collator = DataCollatorForLanguageModeling(tok, mlm=False)

    targs = TrainingArguments(
        output_dir=args.out,
        per_device_train_batch_size=args.micro_batch,
        gradient_accumulation_steps=args.grad_accum,
        num_train_epochs=args.epochs,
        learning_rate=args.lr,
        lr_scheduler_type="cosine",
        warmup_ratio=args.warmup_ratio,
        fp16=(not args.four_bit),
        bf16=args.four_bit,
        logging_steps=10,
        save_strategy="epoch",
        save_total_limit=1,
        report_to="none",
        gradient_checkpointing=True,
        optim="adamw_torch",
        max_grad_norm=args.max_grad_norm,
    )

    trainer = Trainer(
        model=model,
        args=targs,
        train_dataset=ds,
        data_collator=collator,
    )

    print(f"Training: {args.epochs} epochs, batch {args.micro_batch}*{args.grad_accum}")
    trainer.train()
    print(f"Saving adapter to {args.out}")
    model.save_pretrained(args.out)
    tok.save_pretrained(args.out)
    print("Done.")


if __name__ == "__main__":
    main()
