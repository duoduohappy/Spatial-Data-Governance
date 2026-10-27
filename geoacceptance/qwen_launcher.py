"""Qwen Plus Beijing interactive launcher; reads work/private/qwen.env without a key prompt."""
from .deepseek_launcher import main
if __name__=='__main__':raise SystemExit(main(provider='qwen'))
