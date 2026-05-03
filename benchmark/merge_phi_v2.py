#!/usr/bin/env python3
"""Merge phi-sigil-v2 LoRA into the Phi-4 base, save as HF fp16.

ollama's llama-runner segfaults when overlaying our LoRA adapter on a
quantized Phi-4 base (works fine for Qwen split-projection bases).
Workaround: merge offline, ship a single fp16 model file that ollama
quantizes itself.

Usage:
  python merge_phi_v2.py
"""
import os, gc
os.environ["HSA_OVERRIDE_GFX_VERSION"] = "11.0.0"

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from peft import PeftModel

BASE = "microsoft/phi-4"
LORA = "/var/home/marc/Projects/sigil/benchmark/lora_out_phi_v2"
OUT  = "/var/home/marc/Projects/sigil/benchmark/phi_sigil_v2_merged"

print(f"Loading base {BASE} in fp16 on CPU (will fit in RAM, not VRAM)...")
model = AutoModelForCausalLM.from_pretrained(
    BASE,
    torch_dtype=torch.float16,
    device_map="cpu",
    trust_remote_code=True,
)
print(f"Loading LoRA from {LORA}...")
model = PeftModel.from_pretrained(model, LORA)

print("Merging LoRA into base...")
model = model.merge_and_unload()

print(f"Saving merged model to {OUT}...")
os.makedirs(OUT, exist_ok=True)
model.save_pretrained(OUT, safe_serialization=True, max_shard_size="4GB")

# Tokenizer must travel with the model for GGUF conversion
print("Saving tokenizer...")
tok = AutoTokenizer.from_pretrained(BASE, trust_remote_code=True)
tok.save_pretrained(OUT)

print(f"Done. Merged model at {OUT}")
