from .engine import EvidenceStackEngine

def register(ctx):
    ctx.register_context_engine(EvidenceStackEngine())
